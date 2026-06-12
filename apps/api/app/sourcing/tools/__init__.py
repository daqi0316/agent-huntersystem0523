"""Sourcing 工具包 — 候选人搜索工具。

自动注册到 agent_service 的 LLM 工具循环。
通过 registry.py 统一管理 schema + handler。

当前工具:
  - search_platform: 在外部招聘平台搜索候选人（Tavily + 浏览器引擎）
"""

from __future__ import annotations

import logging

from app.sourcing.tools.registry import register_tool, get_tools, get_handlers, clear
from app.sourcing.tools.platform_search import platform_search_tool

logger = logging.getLogger(__name__)

# 模块加载时自动注册
register_tool(platform_search_tool)
logger.info("Sourcing tools initialized: %s", [t.get("function", {}).get("name") for t in get_tools()])

__all__ = [
    "register_tool",
    "get_tools",
    "get_handlers",
    "clear",
]
