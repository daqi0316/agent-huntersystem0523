"""
LinkedIn 候选人搜索器 — 搜索 linkedin.com/in/ 公开个人主页。

能力: Level 2（公开个人主页）
LinkedIn 的 /in/ 个人主页是公开可索引的，包含真实姓名、职位、公司、技能等。
不需要平台登录，即可搜到真实候选人资料。

搜索策略:
  1. 用 Tavily include_domains=["linkedin.com"] + 精心构建的查询搜索
  2. 结果自动过滤，只保留 /in/ 路径的个人主页
  3. 排除公司主页/职位列表/文章/动态等非个人页面
  4. 从 title + content 提取候选人姓名、职位头衔、公司、位置、技能
  5. 多取结果（buffer=4x）确保足够的 /in/ 页面覆盖率
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


class LinkedInSearcher(CandidateSearcher):
    platform = "linkedin"
    display_name = "LinkedIn"
    search_type = "public_profile"
    requires_auth = False
    supported = True

    # LinkedIn 个人主页 URL 模式（多种国际化域名）
    _PROFILE_PATTERN = re.compile(
        r"https?://([a-z]{2}\.)?linkedin\.com/in/[a-zA-Z0-9_-]+"
    )

    # 需要排除的 LinkedIn 非个人页面路径
    _SKIP_PATTERNS = [
        re.compile(r"/in/[a-zA-Z0-9_-]+/details/"),        # /in/xxx/details/...
        re.compile(r"/in/[a-zA-Z0-9_-]+/recent-activity"),  # /in/xxx/recent-activity
        re.compile(r"/in/[a-zA-Z0-9_-]+-[a-zA-Z0-9_-]{20,}"),  # 超长后缀 — 通常是计算机生成的变体
    ]

    # LinkedIn title 格式: "Name - Title at Company - LinkedIn"
    # 示例: "Lei Tang - Co-founder & CTO @Fabi.ai - LinkedIn"
    _TITLE_PATTERN = re.compile(
        r"^(?P<name>[^-]+?)\s*-\s*(?P<title>.+?)\s*-\s*LinkedIn$"
    )
    # 备选: "Name - LinkedIn"（无职位信息）
    _TITLE_SIMPLE = re.compile(
        r"^(?P<name>[^-]+?)\s*-\s*LinkedIn$"
    )

    # 从 content 提取位置的模式
    _LOCATION_PATTERN = re.compile(
        r"(?:📍|🌍|🌏|🌎)?\s*([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\s,·.]+(?:省|市|区|District|Area|Province|County)?)"
        r"(?:\s*[·•]\s*(?:[\dKkMm]+(?:连接|connections|followers?)))?",
    )

    # 技能提取: content 中的标签/关键词
    _SKILL_KEYWORDS = {
        "Python", "Java", "Go", "Rust", "TypeScript", "JavaScript",
        "React", "Vue", "Angular", "Node.js", "Next.js",
        "Machine Learning", "Deep Learning", "AI", "NLP", "LLM",
        "Kubernetes", "Docker", "AWS", "GCP", "Azure",
        "TensorFlow", "PyTorch", "Kafka", "Spark", "Flink",
        "PostgreSQL", "MySQL", "Redis", "MongoDB", "Elasticsearch",
        "Microservices", "System Design", "Architecture",
        "Team Leadership", "Product Management", "Agile", "Scrum",
    }

    async def search(
        self,
        keywords: str,
        location: str = "",
        max_results: int = 5,
    ) -> CandidateSearchResult:
        # 构建更精准的搜索查询
        query = self._build_query(keywords, location)

        # 用 Tavily 在 linkedin.com 域名下搜索
        # buffer=4x 因为很多结果不是 /in/ 页面
        tavily_result = _tavily_search(
            query=query,
            max_results=max_results * 4,
            include_domains=["linkedin.com"],
            include_answer=True,
        )

        if not tavily_result["success"]:
            return CandidateSearchResult(
                success=False,
                platform=self.platform,
                search_type=self.search_type,
                error_message=tavily_result.get("error_message", "搜索失败"),
            )

        sources = tavily_result.get("sources", [])

        # 只保留 /in/ 个人主页链接，过滤非个人页面
        candidates: list[CandidateProfile] = []
        seen_urls: set[str] = set()

        for s in sources:
            url = s.get("url", "").rstrip("/")
            if not self._is_valid_profile_url(url):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = s.get("title", "")
            content = s.get("content", "")

            # 解析候选人信息
            name = self._extract_name(title)
            title_line, company = self._extract_title_and_company(title)
            loc = self._extract_location(content) or ""
            skills = self._extract_skills(content)
            summary = self._extract_summary(content, title, title_line)

            candidates.append(
                CandidateProfile(
                    name=name,
                    title=title_line[:120],
                    company=company,
                    location=loc,
                    profile_url=url,
                    platform=self.platform,
                    source="public_profile",
                    skills=skills[:8],
                    summary=summary[:600] if summary else None,
                )
            )

            if len(candidates) >= max_results:
                break

        return CandidateSearchResult(
            success=True,
            candidates=candidates,
            platform=self.platform,
            search_type=self.search_type,
            total_found=len(candidates),
        )

    def _build_query(self, keywords: str, location: str) -> str:
        parts = [keywords.strip()]
        if location:
            parts.append(location)
        parts.append("LinkedIn profile")
        return " ".join(parts)

    def _is_valid_profile_url(self, url: str) -> bool:
        if not self._PROFILE_PATTERN.match(url):
            return False
        for skip in self._SKIP_PATTERNS:
            if skip.search(url):
                return False
        return True

    @staticmethod
    def _extract_name(title: str) -> str:
        # 标准格式: "Name - Title - LinkedIn"
        m = LinkedInSearcher._TITLE_PATTERN.match(title)
        if m:
            name = m.group("name").strip()
            if name and len(name) < 60:
                return name

        # 简单格式: "Name - LinkedIn"
        m = LinkedInSearcher._TITLE_PATTERN.match(title)
        if m:
            name = m.group("name").strip()
            if name and len(name) < 60:
                return name

        # 尝试简单格式
        m = LinkedInSearcher._TITLE_SIMPLE.match(title)
        if m:
            name = m.group("name").strip()
            if name and len(name) < 60:
                return name

        # 兜底: 取 " - " 分隔首段
        parts = title.split(" - ")
        if parts:
            name = parts[0].strip()
            if name and len(name) < 60 and "LinkedIn" not in name:
                return name
        return title[:50]

    @staticmethod
    def _extract_title_and_company(title: str) -> tuple[str, str | None]:
        """从 LinkedIn 页面标题提取职位头衔和公司。

        "Lei Tang - Co-founder & CTO @Fabi.ai - LinkedIn"
          → ("Co-founder & CTO @Fabi.ai", "Fabi.ai")
        """
        m = LinkedInSearcher._TITLE_PATTERN.match(title)
        if m:
            title_line = m.group("title").strip()
            # 从 title_line 中提取公司名（@ 之后）
            company = None
            at_match = re.search(r"@(.+)", title_line)
            if at_match:
                company = at_match.group(1).strip()
            return title_line, company

        return title[:120], None

    @staticmethod
    def _extract_location(content: str) -> str | None:
        """从 Tavily content 提取位置信息。"""
        if not content:
            return None

        # LinkedIn content 中位置出现在首段附近
        lines = content.split("\n")
        for line in lines[:15]:  # 只看前 15 行
            line = line.strip()
            # 跳过空行/菜单/导航行
            if not line or len(line) < 3:
                continue
            if any(kw in line.lower() for kw in ["navigation", "menu", "search", "linkedin"]):
                continue

            # 用位置标记词匹配
            m = LinkedInSearcher._LOCATION_PATTERN.search(line)
            if m:
                loc = m.group(1).strip()
                # 过滤非位置内容的误匹配
                if len(loc) >= 2 and not any(
                    kw in loc.lower() for kw in ["home", "profile", "about", "experience", "education"]
                ):
                    return loc
        return None

    @staticmethod
    def _extract_skills(content: str) -> list[str]:
        """从 Tavily content 提取技能关键词。"""
        if not content:
            return []
        found: list[str] = []
        for skill in LinkedInSearcher._SKILL_KEYWORDS:
            if skill.lower() in content.lower():
                found.append(skill)
        return found

    @staticmethod
    def _extract_summary(content: str, title: str, title_line: str) -> str:
        """提取最有用的摘要信息。"""
        parts = []
        if title_line:
            parts.append(title_line)
        if content:
            # 取内容的前 300 字符（排除导航行）
            clean_lines = []
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if any(kw in line.lower() for kw in [
                    "navigation", "menu", "search code", "provide feedback",
                    "saved searches", "sign up",
                ]):
                    continue
                clean_lines.append(line)
            clean = " ".join(clean_lines)[:300]
            if clean:
                parts.append(clean)
        return " | ".join(parts) if parts else title[:300]

    def describe_capability(self) -> str:
        return (
            "LinkedIn：搜索公开个人主页（linkedin.com/in/），"
            "可获取真实候选人姓名、职位、公司等资料。无需平台登录。"
        )
