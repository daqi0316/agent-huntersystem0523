"""Knowledge base tool — search_knowledge."""

from __future__ import annotations

import logging

from app.services.knowledge import KnowledgeService
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _handle_search_knowledge(query=""):
    service = KnowledgeService()
    result = await service.query(query=query, top_k=5)
    return {"answer": result.get("answer", ""), "sources": result.get("sources", [])}


tools = [
    {"type": "function", "function": {"name": "search_knowledge", "description": "知识库问答 — 搜索招聘相关的知识文档和资料。", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "查询问题"}}, "required": ["query"]}}},
]

handlers = {"search_knowledge": _handle_search_knowledge}
