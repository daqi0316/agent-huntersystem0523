"""互联网搜索 Skill — 通过 Tavily API 联网搜索实时信息。"""

import logging
import os

from app.skills.base import Skill

logger = logging.getLogger(__name__)

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
                    "description": "搜索关键词，尽量具体（如「2026 年诺贝尔奖」「今日比特币价格」）。",
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果数量上限（默认 5）。",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


async def _web_search(query: str, max_results: int = 5) -> list[dict]:
    """通过 Tavily API 搜索互联网实时信息。"""
    from tavily import TavilyClient

    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return [{"error": "TAVILY_API_KEY 未配置，请联系管理员。"}]

    try:
        client = TavilyClient(api_key=api_key)
        result = client.search(
            query,
            max_results=max_results,
            include_answer=True,
            include_raw_content=False,
        )

        answer = result.get("answer", "")
        sources = result.get("results", [])

        output_parts = []
        if answer:
            output_parts.append(f"【直接答案】{answer}")

        for i, source in enumerate(sources[:max_results]):
            title = source.get("title", "")
            content = source.get("content", "")
            if title and content:
                output_parts.append(f"{i + 1}. {title}: {content[:200]}...")

        if not output_parts:
            return [{"info": "未找到相关结果，请尝试其他关键词。"}]

        return [{"answer": "\n".join(output_parts), "sources": sources}]

    except Exception as e:
        logger.error("Tavily web_search failed: %s", e)
        return [{"error": f"搜索出错：{e}"}]


class WebSearchSkill(Skill):
    """互联网搜索技能 — 基于 Tavily API。"""

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
