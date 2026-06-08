"""System built-in tool registry — 系统内置工具，非可插拔 skill。

每个子模块导出:
  tools: list[dict]     — OpenAI function-calling schema（含 handler 附加字段）
  handlers: dict        — {tool_name: async callable}

区别于 app/skills/（外部插件），app/tools/ 是系统内置能力。
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any, Callable

from app.core.logging import get_logger

logger = get_logger(__name__)

TOOLS_DIR = Path(__file__).parent

_discovered_tools: list[dict] | None = None
_discovered_handlers: dict[str, Callable] | None = None


def discover_tools() -> list[dict]:
    global _discovered_tools
    if _discovered_tools is not None:
        return _discovered_tools
    _discovered_tools = []
    for mod_info in pkgutil.iter_modules([str(TOOLS_DIR)]):
        if mod_info.name in ("__init__", "base"):
            continue
        try:
            mod = importlib.import_module(f"app.tools.{mod_info.name}")
            tools = getattr(mod, "tools", None)
            if tools and isinstance(tools, list):
                for t in tools:
                    name = t.get("function", {}).get("name", "?")
                    _discovered_tools.append(t)
                    logger.debug("Loaded built-in tool: %s", name)
        except Exception:
            logger.exception("Failed to load tool module: %s", mod_info.name)
    logger.info("Discovered %d built-in tools from app/tools/", len(_discovered_tools))
    return _discovered_tools


def discover_handlers() -> dict[str, Callable]:
    global _discovered_handlers
    if _discovered_handlers is not None:
        return _discovered_handlers
    _discovered_handlers = {}
    for mod_info in pkgutil.iter_modules([str(TOOLS_DIR)]):
        if mod_info.name in ("__init__", "base"):
            continue
        try:
            mod = importlib.import_module(f"app.tools.{mod_info.name}")
            handlers = getattr(mod, "handlers", None)
            if handlers and isinstance(handlers, dict):
                for name, handler in handlers.items():
                    _discovered_handlers[name] = handler
                    logger.debug("Registered built-in handler: %s", name)
        except Exception:
            logger.exception("Failed to load handlers from: %s", mod_info.name)
    return _discovered_handlers


def all_tools() -> list[dict]:
    return discover_tools()


def all_handlers() -> dict[str, Callable]:
    return discover_handlers()


def clear_cache() -> None:
    global _discovered_tools, _discovered_handlers
    _discovered_tools = None
    _discovered_handlers = None
