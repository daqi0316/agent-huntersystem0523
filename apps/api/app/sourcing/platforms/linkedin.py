"""LinkedIn 适配器 — httpx + BeautifulSoup 实现"""
from __future__ import annotations

import logging
import random
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.sourcing.platforms.base import PlatformAdapter, CrawlResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.linkedin.com"
_SEARCH_URL = f"{_BASE_URL}/search/results/people"

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def _headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Referer": f"{_BASE_URL}/",
    }


class LinkedInAdapter(PlatformAdapter):
    name = "linkedin"
    display_name = "LinkedIn"
    category = "social"
    anti_crawl_level = 2
    requires_login = False

    async def search(self, keyword: str, **filters) -> CrawlResult:
        """搜索 LinkedIn 公开资料"""
        all_candidates: list[dict[str, Any]] = []
        max_pages = filters.get("max_pages", 2)
        proxy = None
        error_message = None

        if self.proxy_pool:
            proxy = await self.proxy_pool.get_proxy(self.name, self.anti_crawl_level)

        httpx_kwargs: dict[str, Any] = {"headers": _headers(), "timeout": 30.0, "follow_redirects": True}
        if proxy:
            httpx_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**httpx_kwargs) as client:
            for page in range(max_pages):
                params: dict[str, str] = {
                    "keywords": keyword,
                    "page": str(page),
                }
                geo = filters.get("geo")
                if geo:
                    params["geoUrn"] = geo

                try:
                    resp = await client.get(_SEARCH_URL, params=params)
                    resp.raise_for_status()

                    await self.wait_for_rate_limit()
                    self.record_request_result(True, resp.status_code)

                    if "captcha" in resp.text.lower() or "challenge" in resp.text.lower():
                        error_message = "LinkedIn challenge/rate-limit detected"
                        logger.warning("LinkedIn challenge on page %d", page)
                        break

                    candidates = await self.parse_list(resp.text)
                    if not candidates:
                        logger.info("LinkedIn page %d: no more candidates", page)
                        break

                    all_candidates.extend(candidates)
                    logger.info("LinkedIn page %d: found %d candidates", page, len(candidates))

                    await self._delay(3, 6)

                except httpx.HTTPStatusError as e:
                    error_message = f"Page {page}: HTTP {e.response.status_code}"
                    self.record_request_result(False, e.response.status_code)
                    if e.response.status_code in (429, 403):
                        break
                except Exception as e:
                    error_message = f"Page {page}: {e}"
                    logger.exception("LinkedIn search failed on page %d", page)
                    break

        success = bool(all_candidates)
        return CrawlResult(
            success=success,
            candidates=all_candidates,
            error_message=error_message,
            proxy_used=proxy,
        )

    async def get_detail(self, url: str) -> CrawlResult:
        """采集公开资料详情页"""
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
                logger.exception("Failed to get LinkedIn detail: %s", url)
                return CrawlResult(success=False, error_message=str(e))

    async def parse_list(self, html: str) -> list[dict[str, Any]]:
        """从 HTML 解析 LinkedIn 搜索结果"""
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[dict[str, Any]] = []

        cards = (
            soup.select(".reusable-search__result-container")
            or soup.select(".search-result")
            or soup.select("[class*='search-result']")
            or soup.select("li[class*='entity-result']")
        )

        for card in cards:
            try:
                candidate = self._extract_card(card)
                if candidate.get("name"):
                    candidates.append(candidate)
            except Exception as e:
                logger.debug("Skipping LinkedIn card: %s", e)
                continue

        return candidates

    def _extract_card(self, card: Any) -> dict[str, Any]:
        """从单张搜索结果卡片提取字段"""
        name = self._text(card, ".entity-result__title-text a, .actor-name, [class*='title'] a, h3 a")
        title = self._text(card, ".entity-result__primary-subtitle, .subline, [class*='subtitle']")
        company = self._text(card, ".entity-result__secondary-subtitle, [class*='company']")

        link_el = card.select_one("a[href*='/in/']") or card.select_one(".entity-result__title-text a")
        url = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            url = href if href.startswith("http") else f"{_BASE_URL}{href}"

        location = self._text(card, ".entity-result__summary, [class*='location'], .distance")

        return {
            "name": name or "",
            "title": title or "",
            "company": company or "",
            "location": location or "",
            "url": url,
            "platform": self.name,
        }

    async def parse_detail(self, html: str) -> dict[str, Any]:
        """从 HTML 解析公开资料详情"""
        soup = BeautifulSoup(html, "html.parser")

        name = self._text(soup, "h1, .top-card-layout__title, [class*='name']")
        title = self._text(soup, ".top-card-layout__headline, [class*='headline'], .subtitle")
        location = self._text(soup, ".top-card-layout__first-subline, [class*='location']")

        about = None
        about_section = soup.select_one(".about-section, [class*='about'], #about")
        if about_section:
            about = about_section.get_text(strip=True)

        skills = []
        skill_section = soup.select_one(".skills-section, [class*='skill']")
        if skill_section:
            for el in skill_section.select("li, .skill-item, span"):
                t = el.get_text(strip=True)
                if t and len(t) < 100:
                    skills.append(t)

        experiences = []
        exp_section = soup.select_one(".experience-section, [class*='experience']")
        if exp_section:
            for item in exp_section.select("li, .experience-item"):
                experiences.append(item.get_text(strip=True))

        education = None
        edu_section = soup.select_one(".education-section, [class*='education']")
        if edu_section:
            education = edu_section.get_text(strip=True)

        return {
            "name": name,
            "title": title,
            "location": location,
            "skills": skills[:20],
            "experiences": experiences[:10],
            "education": education,
            "description": about,
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
