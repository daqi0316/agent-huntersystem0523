"""GitHub 适配器 — GitHub REST API 实现"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.sourcing.config import sourcing_settings
from app.sourcing.platforms.base import PlatformAdapter, CrawlResult

logger = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"


class GitHubAdapter(PlatformAdapter):
    name = "github"
    display_name = "GitHub"
    category = "code"
    anti_crawl_level = 1
    requires_login = False

    def __init__(self, config: dict[str, Any] | None = None, proxy_pool=None):
        super().__init__(config, proxy_pool)
        self._token: str | None = None
        self._load_token()

    def _load_token(self):
        """加载 GitHub Token（配置或环境变量）"""
        self._token = (
            self.config.get("github_token")
            or getattr(sourcing_settings, "github_token", None)
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Recruitment-System/1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def search(self, keyword: str, **filters) -> CrawlResult:
        """GitHub 用户搜索 + 仓库贡献者搜索"""
        all_candidates: list[dict[str, Any]] = []
        max_pages = filters.get("max_pages", 3)
        proxy = None
        error_message = None

        if self.proxy_pool:
            proxy = await self.proxy_pool.get_proxy(self.name, self.anti_crawl_level)

        httpx_kwargs: dict[str, Any] = {"headers": self._headers(), "timeout": 30.0}
        if proxy:
            httpx_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**httpx_kwargs) as client:
            # Part 1: 搜索用户
            users = await self._search_users(client, keyword, max_pages)
            all_candidates.extend(users)

            # Part 2: 搜索仓库及贡献者
            repos = await self._search_repos(client, keyword, max_pages)
            for repo in repos[:5]:  # 取前5个仓库
                contributors = await self._get_contributors(client, repo)
                all_candidates.extend(contributors)

        success = bool(all_candidates)
        return CrawlResult(
            success=success,
            candidates=all_candidates,
            error_message=error_message,
            proxy_used=proxy,
        )

    async def _search_users(self, client: httpx.AsyncClient, keyword: str, max_pages: int) -> list[dict[str, Any]]:
        """GitHub 用户搜索"""
        results: list[dict[str, Any]] = []

        for page in range(1, max_pages + 1):
            params = {"q": keyword, "per_page": "30", "page": str(page)}
            try:
                resp = await client.get(f"{_API_BASE}/search/users", params=params)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("items", []):
                    login = item.get("login", "")
                    if not login:
                        continue
                    detail = await self._get_user_detail(client, login)
                    if detail:
                        results.append(detail)

                await self.wait_for_rate_limit()
                self.record_request_result(True, resp.status_code)

                remaining = int(resp.headers.get("X-RateLimit-Remaining", 0))
                if remaining < 10:
                    logger.warning("GitHub API rate limit low: %d remaining", remaining)
                    break

                if len(data.get("items", [])) < 30:
                    break

            except httpx.HTTPStatusError as e:
                logger.warning("GitHub user search page %d: HTTP %d", page, e.response.status_code)
                self.record_request_result(False, e.response.status_code)
                break
            except Exception as e:
                logger.exception("GitHub user search page %d failed", page)
                break

        return results

    async def _get_user_detail(self, client: httpx.AsyncClient, login: str) -> dict[str, Any]:
        """获取单个 GitHub 用户详细信息"""
        try:
            resp = await client.get(f"{_API_BASE}/users/{login}")
            resp.raise_for_status()
            data = resp.json()

            # 获取仓库（用于判断技能）
            repos_resp = await client.get(
                f"{_API_BASE}/users/{login}/repos",
                params={"sort": "pushed", "per_page": "10"},
            )
            repos_data = repos_resp.json() if repos_resp.status_code == 200 else []
            languages = set()
            topics = set()
            for repo in repos_data:
                if isinstance(repo, dict):
                    for lang in [repo.get("language")] if repo.get("language") else []:
                        languages.add(lang)
                    for topic in repo.get("topics", []):
                        topics.add(topic)

            bio = data.get("bio") or ""
            company = data.get("company") or ""
            location = data.get("location") or ""

            return {
                "name": data.get("name") or login,
                "login": login,
                "title": bio.split("\n")[0] if bio else f"GitHub Developer @{login}",
                "company": company.strip("@") if company else "",
                "location": location or "",
                "skills": sorted(languages | topics),
                "bio": bio,
                "public_repos": data.get("public_repos", 0),
                "followers": data.get("followers", 0),
                "url": data.get("html_url", f"https://github.com/{login}"),
                "avatar_url": data.get("avatar_url", ""),
                "platform": self.name,
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("GitHub API rate limited on user %s", login)
            return {}
        except Exception as e:
            logger.debug("Failed to get GitHub user %s: %s", login, e)
            return {}

    async def _search_repos(self, client: httpx.AsyncClient, keyword: str, max_pages: int) -> list[dict[str, Any]]:
        """搜索 GitHub 仓库"""
        repos: list[dict[str, Any]] = []

        params = {
            "q": f"{keyword} in:name,description,readme",
            "sort": "stars",
            "order": "desc",
            "per_page": "10",
        }
        try:
            resp = await client.get(f"{_API_BASE}/search/repositories", params=params)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("items", [])[:10]:
                repos.append({
                    "full_name": item.get("full_name", ""),
                    "owner": item.get("owner", {}).get("login", ""),
                    "language": item.get("language"),
                    "topics": item.get("topics", []),
                })
        except Exception as e:
            logger.debug("GitHub repo search failed: %s", e)

        return repos

    async def _get_contributors(self, client: httpx.AsyncClient, repo: dict[str, Any]) -> list[dict[str, Any]]:
        """获取仓库贡献者"""
        results: list[dict[str, Any]] = []
        full_name = repo.get("full_name", "")
        if not full_name:
            return results

        try:
            resp = await client.get(
                f"{_API_BASE}/repos/{full_name}/contributors",
                params={"per_page": "10"},
            )
            if resp.status_code != 200:
                return results

            for item in resp.json():
                login = item.get("login", "")
                if not login:
                    continue
                detail = await self._get_user_detail(client, login)
                if detail and detail.get("name"):
                    # 标记为贡献者类型
                    detail["contribution_repo"] = full_name
                    detail["contributions"] = item.get("contributions", 0)
                    results.append(detail)

        except Exception as e:
            logger.debug("Failed to get contributors for %s: %s", full_name, e)

        return results

    async def get_detail(self, url: str) -> CrawlResult:
        """通过 URL 获取用户详情"""
        # 从 URL 提取 login
        login = url.strip("/").split("/")[-1]
        proxy = None
        if self.proxy_pool:
            proxy = await self.proxy_pool.get_proxy(self.name, self.anti_crawl_level)

        httpx_kwargs: dict[str, Any] = {"headers": self._headers(), "timeout": 30.0}
        if proxy:
            httpx_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**httpx_kwargs) as client:
            detail = await self._get_user_detail(client, login)
            if detail:
                return CrawlResult(success=True, candidates=[detail])
            return CrawlResult(success=False, error_message=f"User {login} not found")

    async def parse_list(self, html: str) -> list[dict[str, Any]]:
        """GitHub API 适配器不需要 HTML 解析"""
        logger.warning("parse_list not needed for GitHubAdapter (uses API)")
        return []

    async def parse_detail(self, html: str) -> dict[str, Any]:
        """GitHub API 适配器不需要 HTML 解析"""
        logger.warning("parse_detail not needed for GitHubAdapter (uses API)")
        return {}
