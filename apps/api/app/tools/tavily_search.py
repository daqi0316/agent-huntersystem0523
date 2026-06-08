"""Tavily internet search tool — 联网搜索，用 Tavily API 获取实时信息。"""

from __future__ import annotations

import logging
from app.core.logging import get_logger
import os

from tavily import TavilyClient

logger = get_logger(__name__)


def _get_tavily_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not configured")
    return TavilyClient(api_key=api_key)


async def _handle_tavily_search(query: str, max_results: int = 5) -> dict:
    """Execute a web search via Tavily and return structured results."""
    try:
        client = _get_tavily_client()
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
            url = source.get("url", "")
            if title and content:
                output_parts.append(f"{i + 1}. {title}: {content[:200]}...")

        if not output_parts:
            return {"answer": "未找到相关结果，请尝试其他关键词。", "sources": []}

        return {
            "answer": "\n".join(output_parts),
            "sources": [{"title": s.get("title", ""), "url": s.get("url", "")} for s in sources[:max_results]],
        }

    except Exception as e:
        logger.error("Tavily search failed: %s", e)
        return {"answer": f"搜索出错：{e}", "sources": []}


# ── Tool schema (OpenAI function-calling format) ─────────────────────────────────

tools = [
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "互联网联网搜索 — 当用户询问实时新闻、实时数据、最新知识、未来天气预报等问题时必须使用。搜索后根据结果回答用户问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，尽量具体（如「2026年诺贝尔奖」「今日比特币价格」「佛山明天天气预报」）。",
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
    },
]

handlers = {"tavily_search": _handle_tavily_search}
