"""Sourcing Tool 注册表 — 统一管理所有 sourcing 工具的 schema + handler。

提供:
  - register_tool(tool) — 注册单个 SourcingTool 实例
  - get_tools() → list[dict] — 所有注册工具的 schema
  - get_handlers() → dict — {tool_name: handler}
  - clear() — 测试用重置
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.sourcing.tools.base import SourcingTool

logger = logging.getLogger(__name__)

_registry: dict[str, SourcingTool] = {}


def register_tool(tool: SourcingTool) -> None:
    """注册一个 SourcingTool 实例。"""
    schema = tool.tool_schema
    name = schema.get("function", {}).get("name", "")
    if not name:
        logger.warning("Attempted to register tool with empty name, skipped")
        return
    _registry[name] = tool
    logger.info("Registered sourcing tool: %s", name)


def get_tools() -> list[dict]:
    """返回所有注册工具的 OpenAI function-calling schema 列表。"""
    return [tool.tool_schema for tool in _registry.values()]


def get_handlers() -> dict[str, Callable[..., Any]]:
    """返回 {tool_name: handler} 映射。"""
    return {name: _make_handler(tool) for name, tool in _registry.items()}


async def call_tool(tool_name: str, **kwargs) -> dict:
    """直接调用已注册工具（供测试/非 LLM 路径使用）。"""
    tool = _registry.get(tool_name)
    if not tool:
        return {"success": False, "error": f"Tool '{tool_name}' not registered"}
    try:
        return await tool.execute(**kwargs)
    except Exception as e:
        logger.exception("Tool %s failed: %s", tool_name, e)
        return {"success": False, "error": str(e)}


def _make_handler(tool: SourcingTool) -> Callable:
    """构造 LLM tool-calling 循环可用的 handler。"""
    async def handler(**kwargs) -> str:
        import json
        result = await tool.execute(**kwargs)
        if result.get("success"):
            summary = result.get("summary", "")
            results = result.get("results", [])
            # 截断结果避免 token 爆炸
            max_display = min(len(results), 10)
            items = results[:max_display]
            return json.dumps({
                "summary": summary,
                "total": result.get("total", 0),
                "items": items,
            }, ensure_ascii=False)
        return json.dumps({"error": result.get("error", "未知错误")}, ensure_ascii=False)

    handler.__name__ = tool.tool_schema.get("function", {}).get("name", "unknown")
    return handler


def clear() -> None:
    """清空注册表（测试用）。"""
    _registry.clear()
