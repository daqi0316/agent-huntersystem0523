"""FakeMCPHost — 单进程 mock host（V-5 测试用）。

用途：
  - unit / integration 测试不启动 13 个真 subprocess
  - dev 单进程模式（--single-process flag）
  - 提供与真 MCPHost 一致的 list_tools / call_tool 接口

实现：
  - 内置 tools 列表 + handlers dict
  - 不走 stdio，直接内存调 handler
  - 同样应用 Pydantic 校验 + 大 result file ref
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from pydantic import ValidationError

from app.mcp_servers._base import (
    maybe_to_file_ref,
    pydantic_from_openai_schema,
    read_file_ref,
)

logger = logging.getLogger(__name__)


class FakeMCPHost:
    """单进程 fake MCP host，不走 stdio。"""

    def __init__(
        self,
        tools: list[dict] | None = None,
        handlers: dict[str, Callable] | None = None,
    ):
        # 工具索引：name → {schema, handler, input_model}
        self._registry: dict[str, dict[str, Any]] = {}
        if tools and handlers:
            for tool in tools:
                self._register_one(tool, handlers)

    def _register_one(self, tool: dict, handlers: dict[str, Callable]) -> None:
        fn = tool["function"]
        name = fn["name"]
        handler = handlers.get(name)
        if not handler:
            raise ValueError(f"Tool {name} has schema but no handler")
        # 优先用 metadata 里的 input_model（V-3 修复），fallback 从 OpenAI schema 推导
        from app.tools.metadata import get_input_model
        input_model = get_input_model(name) or pydantic_from_openai_schema(
            name, fn.get("parameters", {})
        )
        self._registry[name] = {
            "schema": fn,
            "handler": handler,
            "input_model": input_model,
        }

    def register_tool(
        self,
        name: str,
        schema: dict,
        handler: Callable,
        input_model: type | None = None,
    ) -> None:
        """运行时注册 tool（用于动态加载 skill）。"""
        self._registry[name] = {
            "schema": schema,
            "handler": handler,
            "input_model": input_model
            or pydantic_from_openai_schema(name, schema.get("parameters", {})),
        }

    def list_tools(self, format: str = "openai") -> list[dict]:
        """返回所有 tool schemas。

        format: 'openai' (function-calling) | 'mcp' (MCP Tool)
        """
        if format == "mcp":
            return [
                {
                    "name": entry["schema"]["name"],
                    "description": entry["schema"].get("description", ""),
                    "inputSchema": entry["schema"].get("parameters", {}),
                }
                for entry in self._registry.values()
            ]
        return [
            {
                "type": "function",
                "function": entry["schema"],
            }
            for entry in self._registry.values()
        ]

    async def call_tool(self, name: str, arguments: dict) -> Any:
        entry = self._registry.get(name)
        if not entry:
            raise KeyError(f"Unknown tool: {name}")

        # 1. Pydantic 校验
        if entry["input_model"] is not None:
            try:
                validated = entry["input_model"].model_validate(arguments)
                arguments = validated.model_dump(exclude_none=True)
            except ValidationError as e:
                return {
                    "status": "failed",
                    "error": {"code": "VALIDATION_ERROR", "message": e.errors()},
                }

        # 2. 调 handler
        try:
            handler = entry["handler"]
            result = handler(**arguments)
            if asyncio.iscoroutine(result):
                result = await result
        except TypeError as e:
            return {
                "status": "failed",
                "error": {"code": "INVALID_ARGUMENTS", "message": str(e)},
            }
        except Exception as e:
            logger.exception("Handler %s exception: %s", name, e)
            return {
                "status": "failed",
                "error": {"code": "HANDLER_EXCEPTION", "message": str(e)},
            }

        # 3. 大 result 走 file ref
        return maybe_to_file_ref(result)

    def has_tool(self, name: str) -> bool:
        return name in self._registry

    def tool_count(self) -> int:
        return len(self._registry)


def build_fake_host_from_openai_tools(
    tools: list[dict], handlers: dict[str, Callable]
) -> FakeMCPHost:
    """便捷构造：从 (tools, handlers) 构造 FakeMCPHost。"""
    return FakeMCPHost(tools=tools, handlers=handlers)
