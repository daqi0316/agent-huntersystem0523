"""
BOSS直聘适配器 v3 — 使用引擎管理器
基于 BaseBrowserEngine 的三层引擎架构，自动选择 invisible_playwright → browser-use → HTTP
"""

from __future__ import annotations

import logging
from typing import Any

from app.sourcing.platforms.base import PlatformAdapter, CrawlResult
from app.tools.browser_engine import EngineType
from app.tools.browser_engine.manager.engine_manager import EngineManager, EngineStatus

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.zhipin.com"


class BossZhipinAdapterV3(PlatformAdapter):
    """
    BOSS直聘适配器 v3
    引擎策略: invisible_playwright (优先) → browser-use (备用) → HTTP (最后手段)
    """

    name = "boss_zhipin_v3"
    display_name = "BOSS直聘 v3"
    category = "job_board"
    anti_crawl_level = 5
    requires_login = True
    use_stealth = True

    def __init__(self, config: dict[str, Any] | None = None, proxy_pool=None):
        super().__init__(config, proxy_pool)
        self._engine_manager = EngineManager(config.get("engine_manager", {}) if config else {})

    async def health_check(self) -> str:
        """健康检查 — 委托引擎管理器"""
        health = await self._engine_manager.health_check_all()

        if health.get(EngineType.INVISIBLE_PLAYWRIGHT) == EngineStatus.AVAILABLE:
            return "healthy"
        if health.get(EngineType.BROWSER_USE) == EngineStatus.AVAILABLE:
            return "degraded"
        return "down"

    async def search(self, keyword: str, **filters) -> CrawlResult:
        """
        执行搜索 — 引擎管理器自动处理降级逻辑
        """
        search_url = self._build_search_url(keyword, filters)

        result = await self._engine_manager.fetch_with_fallback(
            url=search_url,
            platform_name="boss_zhipin",
            wait_for=".job-card-wrapper",
            timeout=30000,
        )

        if not result.success:
            return CrawlResult(
                success=False,
                error_message=result.error_message,
            )

        candidates = await self.parse_list(result.html)

        return CrawlResult(
            success=True,
            candidates=candidates[:20],
            error_message=result.error_message,
        )

    async def parse_list(self, html: str) -> list[dict[str, Any]]:
        """解析列表页 — 使用 Scrapling Fetcher"""
        from scrapling import Fetcher

        fetcher = Fetcher()
        page = fetcher.get(html)

        candidates = []
        items = page.css(".job-card-wrapper")

        for item in items:
            try:
                candidate = {
                    "name": item.css(".name").text(),
                    "title": item.css(".job-title").text(),
                    "company": item.css(".company-name").text(),
                    "location": item.css(".job-area").text(),
                    "salary": item.css(".salary").text(),
                    "experience": item.css(".tag-list .tag").text(),
                    "detail_url": item.css("a").attr("href"),
                    "source_platform": "boss_zhipin",
                }
                candidates.append(candidate)
            except Exception:
                continue

        return candidates

    async def parse_detail(self, html: str) -> dict[str, Any]:
        """解析详情页"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        name = self._text(soup, ".name, .username, [class*='name']")
        title = self._text(soup, ".title, .job-title, [class*='title']")
        salary = self._text(soup, ".salary, [class*='salary']")
        company = self._text(soup, ".company, .company-name, [class*='company']")

        skill_els = soup.select(".skill-tag, .tag-item, [class*='skill']")
        skills = [t.get_text(strip=True) for t in skill_els if t and t.get_text(strip=True)]

        return {
            "name": name,
            "title": title,
            "salary": salary,
            "company": company,
            "skills": skills,
            "platform": "boss_zhipin_v3",
        }

    async def get_detail(self, url: str) -> CrawlResult:
        """获取详情页 — 通过引擎管理器"""
        result = await self._engine_manager.fetch_with_fallback(
            url=url,
            platform_name="boss_zhipin",
            timeout=30000,
        )

        if not result.success:
            return CrawlResult(success=False, error_message=result.error_message)

        candidate = await self.parse_detail(result.html)
        candidate["detail_url"] = url

        return CrawlResult(
            success=True,
            candidates=[candidate],
        )

    def _build_search_url(self, keyword: str, filters: dict) -> str:
        """构建搜索 URL"""
        import urllib.parse

        query = urllib.parse.quote(keyword)
        url = f"{_BASE_URL}/web/geek/job?query={query}"

        if city := filters.get("location"):
            url += f"&city={city}"
        if exp := filters.get("experience_years"):
            url += f"&experience={exp}"

        return url

    async def cleanup(self):
        """清理资源"""
        await self._engine_manager.close_all()

    @staticmethod
    def _text(soup: Any, selector: str) -> str | None:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            return text if text else None
        return None
