"""脉脉适配器 — httpx + BeautifulSoup 实现"""
from __future__ import annotations

import json
import logging
import random
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.sourcing.platforms.base import PlatformAdapter, CrawlResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://maimai.cn"
_SEARCH_URL = f"{_BASE_URL}/search/talent"
_DETAIL_URL = f"{_BASE_URL}/profile"

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class MaimaiAdapter(PlatformAdapter):
    name = "maimai"
    display_name = "脉脉"
    category = "social"
    anti_crawl_level = 3
    requires_login = True

    def __init__(self, config: dict[str, Any] | None = None, proxy_pool=None, account_manager=None):
        super().__init__(config, proxy_pool)
        self.account_manager = account_manager
        self._cookie_str: str | None = None

    async def _ensure_cookie(self) -> str | None:
        """从 AccountManager 获取脉脉 Cookie"""
        if self._cookie_str:
            return self._cookie_str
        if self.account_manager:
            account = await self.account_manager.acquire(self.name)
            if account and account.encrypted_cookies:
                from app.sourcing.account_manager import decrypt_cookie
                try:
                    raw = decrypt_cookie(account.encrypted_cookies)
                    cookies = json.loads(raw)
                    if isinstance(cookies, list):
                        self._cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies if "name" in c and "value" in c)
                    elif isinstance(cookies, dict):
                        self._cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
                    logger.info("Loaded maimai cookie from account %s", account.display_name)
                except Exception as e:
                    logger.warning("Failed to decrypt maimai cookie: %s", e)
        return self._cookie_str

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{_BASE_URL}/",
            "Origin": _BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
        }
        if self._cookie_str:
            headers["Cookie"] = self._cookie_str
        return headers

    async def search(self, keyword: str, **filters) -> CrawlResult:
        """搜索脉脉候选人列表"""
        await self._ensure_cookie()

        all_candidates: list[dict[str, Any]] = []
        max_pages = filters.get("max_pages", 3)
        proxy = None
        error_message = None

        if self.proxy_pool:
            proxy = await self.proxy_pool.get_proxy(self.name, self.anti_crawl_level)

        httpx_kwargs: dict[str, Any] = {"headers": self._headers(), "timeout": 30.0, "follow_redirects": True}
        if proxy:
            httpx_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**httpx_kwargs) as client:
            for page in range(1, max_pages + 1):
                params: dict[str, str] = {
                    "query": keyword,
                    "page": str(page),
                    "page_size": "20",
                }
                city = filters.get("city")
                if city:
                    params["city"] = city

                try:
                    resp = await client.get(_SEARCH_URL, params=params)
                    resp.raise_for_status()

                    await self.wait_for_rate_limit()
                    self.record_request_result(True, resp.status_code)

                    data = resp.json()
                    items = data.get("data", {}).get("list", data.get("list", []))
                    if not items:
                        logger.info("Maimai page %d: no more candidates", page)
                        break

                    for item in items:
                        candidate = self._parse_search_item(item)
                        if candidate.get("name"):
                            all_candidates.append(candidate)

                    logger.info("Maimai page %d: found %d candidates", page, len(items))

                    if len(items) < 20:
                        break

                    await self._delay(2, 4)

                except httpx.HTTPStatusError as e:
                    error_message = f"Page {page}: HTTP {e.response.status_code}"
                    self.record_request_result(False, e.response.status_code)
                    if e.response.status_code in (401, 403):
                        logger.warning("Maimai auth failed, cookie may be expired")
                        if self.account_manager:
                            await self.account_manager.rotate(self.name, "")
                        break
                    if e.response.status_code in (429,):
                        break
                except Exception as e:
                    error_message = f"Page {page}: {e}"
                    logger.exception("Maimai search failed on page %d", page)
                    break

        success = bool(all_candidates)
        return CrawlResult(
            success=success,
            candidates=all_candidates,
            error_message=error_message,
            proxy_used=proxy,
        )

    def _parse_search_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """解析脉脉搜索结果的 JSON 条目"""
        profile = item.get("profile", item.get("user", {}))
        return {
            "name": profile.get("name") or item.get("name", ""),
            "title": profile.get("title") or item.get("title") or item.get("headline", ""),
            "company": profile.get("company") or item.get("company", ""),
            "location": profile.get("city") or item.get("city", ""),
            "skills": profile.get("skills", item.get("skills", [])),
            "education": profile.get("education", ""),
            "summary": profile.get("summary", item.get("desc", "")),
            "url": f"{_DETAIL_URL}/{profile.get('id', '')}" if profile.get("id") else "",
            "platform": self.name,
        }

    async def get_detail(self, url: str) -> CrawlResult:
        """采集候选人详情页"""
        proxy = None
        if self.proxy_pool:
            proxy = await self.proxy_pool.get_proxy(self.name, self.anti_crawl_level)

        httpx_kwargs: dict[str, Any] = {"headers": self._headers(), "timeout": 30.0, "follow_redirects": True}
        if proxy:
            httpx_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**httpx_kwargs) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    data = resp.json()
                    candidate = self._parse_search_item(data.get("data", data))
                    return CrawlResult(success=True, candidates=[candidate] if candidate.get("name") else [])
                else:
                    detail = await self.parse_detail(resp.text)
                    return CrawlResult(success=True, candidates=[detail] if detail else [])

            except Exception as e:
                logger.exception("Failed to get maimai detail: %s", url)
                return CrawlResult(success=False, error_message=str(e))

    async def parse_list(self, html: str) -> list[dict[str, Any]]:
        """HTML 版列表解析（兜底）"""
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[dict[str, Any]] = []
        cards = soup.select(".user-card, [class*='card'], .talent-item")
        for card in cards:
            try:
                name = self._text(card, ".name, .username, [class*='name']")
                title = self._text(card, ".title, [class*='title']")
                company = self._text(card, ".company, [class*='company']")
                if name or title:
                    candidates.append({
                        "name": name,
                        "title": title,
                        "company": company,
                        "platform": self.name,
                    })
            except Exception:
                continue
        return candidates

    async def parse_detail(self, html: str) -> dict[str, Any]:
        """从 HTML 解析候选人详情（兜底）"""
        soup = BeautifulSoup(html, "html.parser")
        name = self._text(soup, ".name, .username, [class*='name'], h1")
        title = self._text(soup, ".title, [class*='title']")
        company = self._text(soup, ".company, [class*='company']")
        skill_els = soup.select(".skill-tag, .tag, [class*='skill']")
        skills = [t.get_text(strip=True) for t in skill_els if t and t.get_text(strip=True)]

        return {
            "name": name,
            "title": title,
            "company": company,
            "skills": skills,
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
