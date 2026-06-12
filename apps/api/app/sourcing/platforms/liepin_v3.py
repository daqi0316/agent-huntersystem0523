"""
猎聘适配器 v3 — 使用引擎管理器
基于 BaseBrowserEngine 的三层引擎架构
"""

from __future__ import annotations

import logging
from typing import Any

from app.sourcing.platforms.base import PlatformAdapter, CrawlResult
from app.tools.browser_engine.manager.engine_manager import EngineManager

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.liepin.com"


class LiepinAdapterV3(PlatformAdapter):
    """
    猎聘适配器 v3
    引擎策略: invisible_playwright (优先) → browser-use (备用) → HTTP (最后手段)
    """

    name = "liepin_v3"
    display_name = "猎聘 v3"
    category = "job_board"
    anti_crawl_level = 5
    requires_login = False

    def __init__(self, config: dict[str, Any] | None = None, proxy_pool=None):
        super().__init__(config, proxy_pool)
        self._engine_manager = EngineManager(config.get("engine_manager", {}) if config else {})

    async def search(self, keyword: str, **filters) -> CrawlResult:
        """执行搜索 — 引擎管理器自动处理降级"""
        search_url = self._build_search_url(keyword, filters)

        result = await self._engine_manager.fetch_with_fallback(
            url=search_url,
            platform_name="liepin",
            wait_for=".job-list-item",
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
        )

    async def parse_list(self, html: str) -> list[dict[str, Any]]:
        """解析列表页"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        candidates = []

        cards = (
            soup.select(".job-list-item")
            or soup.select("[class*='resume-card']")
            or soup.select("[class*='job-card']")
            or soup.select("li[class*='item']")
        )

        for card in cards:
            try:
                candidate = self._extract_card(card)
                if candidate.get("name") or candidate.get("title"):
                    candidates.append(candidate)
            except Exception:
                continue

        return candidates

    def _extract_card(self, card: Any) -> dict[str, Any]:
        name = self._text(card, ".name, .username, [class*='name'], h3")
        title = self._text(card, ".title, .job-title, [class*='title']")
        salary = self._text(card, ".salary, [class*='salary'], [class*='pay']")
        company = self._text(card, ".company, .company-name, [class*='company']")
        tags = [
            t.get_text(strip=True)
            for t in card.select(".tag, .tag-item, [class*='tag'], span[class]")
            if t.get_text(strip=True) and len(t.get_text(strip=True)) < 20
        ]

        link_el = card.select_one("a[href]")
        url = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            url = href if href.startswith("http") else f"{_BASE_URL}{href}"

        return {
            "name": name,
            "title": title,
            "salary": salary,
            "company": company,
            "tags": tags[:10],
            "url": url,
            "platform": "liepin_v3",
        }

    async def get_detail(self, url: str) -> CrawlResult:
        """获取详情页"""
        result = await self._engine_manager.fetch_with_fallback(
            url=url,
            platform_name="liepin",
            timeout=30000,
        )

        if not result.success:
            return CrawlResult(success=False, error_message=result.error_message)

        candidate = await self.parse_detail(result.html)
        candidate["detail_url"] = url

        return CrawlResult(success=True, candidates=[candidate])

    async def parse_detail(self, html: str) -> dict[str, Any]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        name = self._text(soup, ".name, .username, [class*='name'], h1")
        title = self._text(soup, ".title, .job-title, [class*='title']")
        salary = self._text(soup, ".salary, [class*='salary'], [class*='pay']")
        company = self._text(soup, ".company, .company-name, [class*='company']")

        skill_els = soup.select(".skill-tag, .tag-item, [class*='skill'], .keyword")
        skills = [t.get_text(strip=True) for t in skill_els if t and t.get_text(strip=True)]

        return {
            "name": name,
            "title": title,
            "salary": salary,
            "company": company,
            "skills": skills,
            "platform": "liepin_v3",
        }

    def _build_search_url(self, keyword: str, filters: dict) -> str:
        import urllib.parse
        params = {
            "key": keyword,
            "dq": filters.get("city", "全国"),
            "currentPage": "1",
            "pageSize": "40",
        }
        return f"{_BASE_URL}/zhaopin?{urllib.parse.urlencode(params)}"

    async def cleanup(self):
        await self._engine_manager.close_all()

    @staticmethod
    def _text(soup: Any, selector: str) -> str | None:
        try:
            el = soup.select_one(selector) if hasattr(soup, "select_one") else None
            if el:
                text = el.get_text(strip=True)
                return text if text else None
        except Exception:
            pass
        return None
