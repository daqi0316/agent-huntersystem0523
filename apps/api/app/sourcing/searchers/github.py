"""
GitHub 候选人搜索器 — 搜索 GitHub 公开个人主页。

能力: Level 2（公开个人主页）
GitHub 的公开 profile 页面包含姓名、bio、公司、位置、技术栈等信息。
不需要平台登录。

搜索策略:
  1. 用 Tavily include_domains=["github.com"] 聚焦 GitHub 域名
  2. 结果过滤只保留 github.com/<username> 单段路径（非 repo/org/page）
  3. 排除已知组织账号、导航路径等非个人页面
  4. 从 title/content 提取候选人姓名、bio、位置、公司
  5. 多轮查询: 不同关键词角度提高覆盖率

注意: GitHub profile 页面 SEO 文本较少，结果不如 LinkedIn 丰富。
      适合技术岗位的补充寻源。
"""

from __future__ import annotations

import logging
import re

from app.sourcing.searchers.base import (
    CandidateSearcher,
    CandidateSearchResult,
    CandidateProfile,
    _tavily_search,
)

logger = logging.getLogger(__name__)


class GitHubSearcher(CandidateSearcher):
    platform = "github"
    display_name = "GitHub"
    search_type = "public_profile"
    requires_auth = False
    supported = True

    # 只匹配 github.com/<username>（单段路径，非 repo）
    _PROFILE_PATTERN = re.compile(r"^https://github\.com/([a-zA-Z0-9._-]+)$")
    # 排除已知非用户路径和知名组织
    _SKIP_NAMES: set[str] = {
        "orgs", "about", "marketplace", "explore", "settings",
        "notifications", "pricing", "issues", "pull", "features",
        "enterprise", "security", "solutions", "sponsors", "topics",
        "collections", "events", "trending", "blog", "stars",
        "developer", "readme", "login", "signup", "support",
        "site", "customer-stories", "team", "resources",
        "contact", "pulls", "discussions", "codespaces", "packages",
        "actions", "projects", "wikis", "insights",
        "google", "microsoft", "apple", "meta", "amazon", "netflix",
        "tencent", "alibaba", "baidu", "bytedance", "huawei", "xiaomi",
        "apache", "nvidia", "intel", "ibm", "oracle", "cisco",
        "github", "vercel", "docker", "kubernetes", "linux",
        "openai", "anthropics", "deepmind", "huggingface",
        "pytorch", "tensorflow", "nodejs", "typescript",
        "spring-projects", "rails", "django", "flask",
        "aws", "gcp", "azure", "cloudflare", "hashicorp", "elastic",
    }

    # 多轮查询模板
    _QUERY_TEMPLATES = [
        "{keywords} GitHub {location}",
        "{keywords} github.com profile {location}",
    ]

    async def search(
        self,
        keywords: str,
        location: str = "",
        max_results: int = 5,
    ) -> CandidateSearchResult:
        all_candidates: list[CandidateProfile] = []
        seen_urls: set[str] = set()

        for tmpl in self._QUERY_TEMPLATES:
            query = tmpl.format(
                keywords=keywords.strip(),
                location=location or "",
            ).strip()
            query = re.sub(r"\s+", " ", query)

            candidates = await self._search_round(
                query=query,
                max_results=max_results - len(all_candidates),
                seen_urls=seen_urls,
            )
            for c in candidates:
                if c.profile_url not in seen_urls:
                    seen_urls.add(c.profile_url)
                    all_candidates.append(c)

            if len(all_candidates) >= max_results:
                break

        return CandidateSearchResult(
            success=bool(all_candidates),
            candidates=all_candidates[:max_results],
            platform=self.platform,
            search_type=self.search_type,
            total_found=min(len(all_candidates), max_results),
        )

    async def _search_round(
        self,
        query: str,
        max_results: int,
        seen_urls: set[str] | None = None,
    ) -> list[CandidateProfile]:
        tavily_result = _tavily_search(
            query=query,
            max_results=max(15, max_results * 5),
            include_domains=["github.com"],
            include_answer=True,
        )

        if not tavily_result["success"]:
            return []

        sources = tavily_result.get("sources", [])
        candidates: list[CandidateProfile] = []
        done_urls: set[str] = seen_urls or set()

        for s in sources:
            url = s.get("url", "").rstrip("/")
            if not self._is_valid_profile_url(url):
                continue
            if url in done_urls:
                continue
            done_urls.add(url)

            title = s.get("title", "")
            content = s.get("content", "")

            name, gh_name = self._extract_name(title)
            company = self._extract_company(content)
            gh_location = self._extract_location(content)
            bio = self._extract_bio(content)

            candidates.append(
                CandidateProfile(
                    name=name or gh_name,
                    title=f"GitHub: {bio or gh_name}"[:120] if bio else f"GitHub Developer: {gh_name}",
                    company=company,
                    location=gh_location or "",
                    profile_url=url,
                    platform=self.platform,
                    source="public_profile",
                    summary=bio or content[:400] if content else None,
                )
            )

            if len(candidates) >= max_results:
                break

        return candidates

    @staticmethod
    def _is_valid_profile_url(url: str) -> bool:
        m = GitHubSearcher._PROFILE_PATTERN.match(url)
        if not m:
            return False
        return m.group(1).lower() not in GitHubSearcher._SKIP_NAMES

    @staticmethod
    def _extract_name(title: str) -> tuple[str | None, str]:
        clean = re.sub(r"\s*[··]\s*GitHub\s*$", "", title).strip()
        paren_match = re.search(r"\(([^)]+)\)", clean)
        if paren_match:
            return paren_match.group(1).strip(), clean.split("(")[0].strip()
        if " " in clean and re.match(r"^[A-Z][a-z]", clean):
            return clean, clean
        return None, clean

    @staticmethod
    def _extract_location(content: str) -> str | None:
        if not content:
            return None
        for line in content.split("\n")[:20]:
            line = line.strip()
            if not line or len(line) < 2:
                continue
            if any(kw in line.lower() for kw in
                   ["navigation", "menu", "search code", "linkedin",
                    "saved searches", "sign up", "provide feedback",
                    "blocks:", "insights"]):
                continue
            if re.search(r"[A-Za-z\u4e00-\u9fff]{4,}", line):
                if not any(kw in line.lower() for kw in
                           ["followers", "repositories", "stars", "forked",
                            "pinned", "readme", "license", "contributing",
                            "overview", "activity"]):
                    return line[:60]
        return None

    @staticmethod
    def _extract_company(content: str) -> str | None:
        if not content:
            return None
        for line in content.split("\n")[:20]:
            line = line.strip()
            if line.startswith("@") and len(line) > 3:
                org = line[1:].strip()
                if re.match(r"^[a-zA-Z0-9_.-]{2,}$", org):
                    return org
        return None

    @staticmethod
    def _extract_bio(content: str) -> str | None:
        if not content:
            return None
        for line in content.split("\n"):
            line = line.strip()
            if len(line) < 15 or len(line) > 200:
                continue
            if any(kw in line.lower() for kw in
                   ["navigation", "menu", "search code", "provide feedback",
                    "saved searches", "sign up", "blocks:", "security",
                    "footer", "cookie", "privacy", "terms", "all rights reserved"]):
                continue
            if re.search(
                r"(?:is\s+a|works\s+on|building|focus|passionate|"
                r"engineer|developer|researcher|scientist|founder|cto|"
                r"lead|architect|expert|creating|designing|building)",
                line, re.IGNORECASE,
            ):
                return line[:200]
        return None

    def describe_capability(self) -> str:
        return (
            "GitHub：搜索 GitHub 公开个人主页（github.com/<username>），"
            "可获取开发者姓名、bio、公司、位置。无需平台登录。适合技术岗位补充寻源。"
        )
