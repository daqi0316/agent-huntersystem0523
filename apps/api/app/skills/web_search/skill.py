"""互联网搜索 Skill — 通过 DuckDuckGo 免费搜索接口获取实时信息。"""

import logging
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from app.skills.base import Skill

logger = logging.getLogger(__name__)

_DDG_URL = "https://html.duckduckgo.com/html/?q={query}"

_TOOL_SEARCH = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索互联网上的最新信息。当用户询问新闻、实时数据、未来天气预报、知识类问题时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，尽量具体（如「2026 年诺贝尔奖」「今日比特币价格」）",
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果数量上限（默认 5）",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


async def _web_search(query: str, max_results: int = 5) -> list[dict]:
    """通过 DuckDuckGo HTML 搜索获取结果。"""
    url = _DDG_URL.format(query=quote_plus(query))
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers, follow_redirects=True)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for item in soup.select(".result"):
        if len(results) >= max_results:
            break

        title_el = item.select_one(".result__title a")
        snippet_el = item.select_one(".result__snippet")

        if not title_el:
            continue

        results.append({
            "title": title_el.get_text(strip=True),
            "url": title_el.get("href", ""),
            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
        })

    return results if results else [{"info": "未找到相关结果，请尝试修改关键词。"}]


class WebSearchSkill(Skill):
    """互联网搜索技能。"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "互联网实时搜索，获取新闻、知识、数据等最新信息"

    def get_tools(self) -> list[dict]:
        return [_TOOL_SEARCH]

    def get_handlers(self) -> dict:
        return {"web_search": _web_search}


skill = WebSearchSkill()
