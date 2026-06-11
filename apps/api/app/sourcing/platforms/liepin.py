"""猎聘适配器 — httpx + BeautifulSoup 实现"""
from __future__ import annotations

import logging
import random
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.sourcing.platforms.base import PlatformAdapter, CrawlResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.liepin.com"
_SEARCH_URL = f"{_BASE_URL}/zhaopin"
_DETAIL_URL = f"{_BASE_URL}/resume"

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


def _headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": _BASE_URL,
    }


class LiepinAdapter(PlatformAdapter):
    name = "liepin"
    display_name = "猎聘"
    category = "job_board"
    anti_crawl_level = 3
    requires_login = False

    async def search(self, keyword: str, **filters) -> CrawlResult:
        """搜索猎聘候选人列表，翻页采集"""
        all_candidates: list[dict[str, Any]] = []
        max_pages = filters.get("max_pages", 3)
        proxy = None
        error_message = None

        if self.proxy_pool:
            proxy = await self.proxy_pool.get_proxy(self.name, self.anti_crawl_level)

        httpx_kwargs: dict[str, Any] = {"headers": _headers(), "timeout": 30.0, "follow_redirects": True}
        if proxy:
            httpx_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**httpx_kwargs) as client:
            for page in range(1, max_pages + 1):
                params: dict[str, str] = {
                    "key": keyword,
                    "dq": filters.get("city", "全国"),
                    "currentPage": str(page),
                    "pageSize": "40",
                }
                try:
                    resp = await client.get(_SEARCH_URL, params=params)
                    resp.raise_for_status()

                    await self.wait_for_rate_limit()
                    self.record_request_result(True, resp.status_code)

                    if "captcha" in resp.text.lower() or "verify" in resp.text.lower():
                        error_message = f"Captcha triggered on page {page}"
                        logger.warning("Liepin captcha on page %d", page)
                        break

                    candidates = await self.parse_list(resp.text)
                    if not candidates:
                        logger.info("Liepin page %d: no more candidates", page)
                        break

                    all_candidates.extend(candidates)
                    logger.info("Liepin page %d: found %d candidates", page, len(candidates))

                    # 页间间隔
                    await self._delay(2, 5)

                except httpx.HTTPStatusError as e:
                    error_message = f"Page {page}: HTTP {e.response.status_code}"
                    self.record_request_result(False, e.response.status_code)
                    if e.response.status_code in (429, 403):
                        break
                except Exception as e:
                    error_message = f"Page {page}: {e}"
                    logger.exception("Liepin search failed on page %d", page)
                    break

        success = bool(all_candidates)
        return CrawlResult(
            success=success,
            candidates=all_candidates,
            error_message=error_message,
            proxy_used=proxy,
        )

    async def get_detail(self, url: str) -> CrawlResult:
        """采集候选人详情页"""
        proxy = None
        if self.proxy_pool:
            proxy = await self.proxy_pool.get_proxy(self.name, self.anti_crawl_level)

        httpx_kwargs: dict[str, Any] = {"headers": _headers(), "timeout": 30.0, "follow_redirects": True}
        if proxy:
            httpx_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**httpx_kwargs) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                detail = await self.parse_detail(resp.text)
                return CrawlResult(success=True, candidates=[detail] if detail else [])
            except Exception as e:
                logger.exception("Failed to get liepin detail: %s", url)
                return CrawlResult(success=False, error_message=str(e))

    async def parse_list(self, html: str) -> list[dict[str, Any]]:
        """从 HTML 解析候选人列表"""
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[dict[str, Any]] = []

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
            except Exception as e:
                logger.debug("Skipping liepin card parse: %s", e)
                continue

        return candidates

    def _extract_card(self, card: Any) -> dict[str, Any]:
        """从单张卡片提取字段"""
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
            "platform": self.name,
        }

    async def parse_detail(self, html: str) -> dict[str, Any]:
        """从 HTML 解析候选人详情"""
        soup = BeautifulSoup(html, "html.parser")

        name = self._text(soup, ".name, .username, [class*='name'], h1")
        title = self._text(soup, ".title, .job-title, [class*='title']")
        salary = self._text(soup, ".salary, [class*='salary'], [class*='pay']")
        company = self._text(soup, ".company, .company-name, [class*='company']")

        skill_els = soup.select(".skill-tag, .tag-item, [class*='skill'], .keyword")
        skills = [t.get_text(strip=True) for t in skill_els if t and t.get_text(strip=True)]

        experiences = []
        exp_section = soup.select_one(".experience, .work-experience, [class*='experience']")
        if exp_section:
            for item in exp_section.select("li, .item, .time-line-item"):
                experiences.append(item.get_text(strip=True))

        education = None
        edu_section = soup.select_one(".education, [class*='education']")
        if edu_section:
            education = edu_section.get_text(strip=True)

        description = None
        desc_section = soup.select_one(".description, .personal-desc, [class*='desc'], .summary")
        if desc_section:
            description = desc_section.get_text(strip=True)

        return {
            "name": name,
            "title": title,
            "salary": salary,
            "company": company,
            "skills": skills,
            "experiences": experiences[:10],
            "education": education,
            "description": description,
            "platform": self.name,
        }

    async def _delay(self, min_sec: float = 1, max_sec: float = 3):
        import asyncio
        await asyncio.sleep(random.uniform(min_sec, max_sec))

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
