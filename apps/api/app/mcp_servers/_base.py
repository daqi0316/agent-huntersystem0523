"""MCP server 通用框架 — 基于 FastMCP (mcp>=1.0)。

设计目标（v4 V-1~V-6 修复落地）：
  - 真进程：每个 server 跑独立子进程，stdio 通信
  - Pydantic 强校验：handler 调前 model_validate（V-3）
  - 大 result 走 file ref（V-2）：>1MB 序列化写文件，避免 stdout pipe 死锁
  - 工具 metadata 注入：capability / version / requires_role → meta 字段
  - 自动从 OpenAI schema 推导 Pydantic InputModel（兜底）
  - 显式声明 InputModel 优先（tool_meta 装饰器）

用法 A（OpenAI 风格 schema，自动推导 Pydantic）：
    @entrypoint("mcp-utils", capability="read", version="1.0.0")
    def main():
        return tools_list, handlers_dict

用法 B（显式 Pydantic，更安全）：
    class CalculateInput(BaseModel):
        expression: str = Field(..., description="数学表达式")

    @tool_meta(input_model=CalculateInput, capability="read", version="1.0.0")
    def tools():
        return [...]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError, create_model

try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover
    MCP_AVAILABLE = False
    FastMCP = None  # type: ignore

logger = logging.getLogger(__name__)

# ── V-2 大 result 走 file ref ─────────────────────────────────────────────
LARGE_RESULT_THRESHOLD = 1 * 1024 * 1024  # 1MB
LARGE_RESULT_DIR = Path(os.getenv("MCP_LARGE_RESULT_DIR", "/tmp/mcp_large_results"))
LARGE_RESULT_DIR.mkdir(parents=True, exist_ok=True)


def maybe_to_file_ref(result: Any) -> Any:
    """结果 >1MB 走 file ref，避免 stdout pipe 满。

    file ref 格式：
        {"_type": "file_ref", "path": "/tmp/xxx.json", "size": N, "preview": "..."}

    host 端用 read_file_ref() 还原。
    """
    try:
        if isinstance(result, (dict, list)):
            serialized = json.dumps(result, ensure_ascii=False, default=str)
        else:
            serialized = str(result)
        if len(serialized) > LARGE_RESULT_THRESHOLD:
            path = LARGE_RESULT_DIR / f"{uuid.uuid4().hex}.json"
            path.write_text(serialized, encoding="utf-8")
            logger.warning(
                "Large result (%.1f KB) → file ref %s",
                len(serialized) / 1024,
                path,
            )
            return {
                "_type": "file_ref",
                "path": str(path),
                "size": len(serialized),
                "preview": serialized[:500] + "...",
            }
    except (TypeError, ValueError) as e:
        logger.debug("maybe_to_file_ref: serialization failed, returning as-is: %s", e)
    return result


def read_file_ref(ref: Any) -> Any:
    """host 端还原 file ref 形式的 result。"""
    if isinstance(ref, dict) and ref.get("_type") == "file_ref":
        path = Path(ref["path"])
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        finally:
            path.unlink(missing_ok=True)
    return ref


# ── Pydantic 兜底：OpenAI schema → BaseModel ──────────────────────────────
_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def pydantic_from_openai_schema(tool_name: str, schema: dict) -> type[BaseModel] | None:
    """从 OpenAI function-calling JSON schema 推导 Pydantic BaseModel。

    支持 type/description/default/required。
    enum / pattern / min / max 等高级约束**不**自动推导（需要显式 InputModel）。
    """
    if not schema or schema.get("type") != "object":
        return None
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    if not properties:
        return None
    fields: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        py_type = _TYPE_MAP.get(prop_schema.get("type", "string"), str)
        description = prop_schema.get("description", "")
        if prop_name in required:
            fields[prop_name] = (py_type, Field(..., description=description))
        else:
            default = prop_schema.get("default", None)
            fields[prop_name] = (py_type | None, Field(default=default, description=description))
    model_name = f"{tool_name}_Input"
    return create_model(model_name, **fields)  # type: ignore[return-value]


# ── handler 安全调用 + 大 result 自动 file ref ────────────────────────────
async def _safe_invoke(handler: Callable, arguments: dict) -> Any:
    try:
        result = handler(**arguments)
        if asyncio.iscoroutine(result):
            result = await result
    except TypeError as e:
        return {
            "status": "failed",
            "error": {"code": "INVALID_ARGUMENTS", "message": str(e)},
        }
    except Exception as e:
        logger.exception("Handler exception: %s", e)
        return {
            "status": "failed",
            "error": {
                "code": "HANDLER_EXCEPTION",
                "message": str(e),
                "traceback": traceback.format_exc()[:500],
            },
        }
    return maybe_to_file_ref(result)


# ── 注册一个 tool 到 FastMCP server ──────────────────────────────────────
def _register_one_tool(mcp: FastMCP, entry: dict) -> None:
    tool_name = entry["name"]
    schema = entry["schema"]
    handler = entry["handler"]
    explicit_input_model = entry.get("input_model")
    capability = entry.get("capability", "read")
    version = entry.get("version", "1.0.0")
    requires_role = entry.get("requires_role")

    # 优先级：显式 input_model > OpenAI schema 推导
    input_model = explicit_input_model or pydantic_from_openai_schema(
        tool_name, schema.get("parameters", {})
    )

    meta: dict[str, Any] = {
        "capability": capability,
        "version": version,
    }
    if requires_role:
        meta["requires_role"] = requires_role

    # FastMCP 1.27 总是把 args 包成 {"arguments": {...}}（这是 SDK 设计，无法 escape）
    # handler 内部把 arguments 字段解开再 Pydantic 校验
    async def wrapped(arguments: dict) -> Any:
        # 解包 FastMCP 包装：{"arguments": {"x": 1}} → {"x": 1}
        # 也兼容直接传 dict（未来 FastMCP 改设计 / 测试场景）
        if (
            isinstance(arguments, dict)
            and len(arguments) == 1
            and "arguments" in arguments
            and isinstance(arguments["arguments"], dict)
        ):
            inner = arguments["arguments"]
        else:
            inner = arguments

        # 1. Pydantic 校验（如果声明了 input_model）
        if input_model is not None:
            try:
                validated = input_model.model_validate(inner)
                inner = validated.model_dump(exclude_none=True)
            except ValidationError as e:
                return {
                    "status": "failed",
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": e.errors(),
                    },
                }

        # 2. 调真实 handler
        return await _safe_invoke(handler, inner)

    wrapped.__name__ = tool_name
    wrapped.__doc__ = schema.get("description", "")

    mcp.tool(
        name=tool_name,
        description=schema.get("description", ""),
        meta=meta,
    )(wrapped)


# ── 公开 API ──────────────────────────────────────────────────────────────
def build_mcp_server(
    name: str,
    tool_entries: list[dict],
    *,
    server_version: str = "1.0.0",
) -> FastMCP:
    """从 tool_entries 构建 FastMCP server 实例。"""
    if not MCP_AVAILABLE:
        raise ImportError(
            "mcp SDK not installed. Run: uv pip install 'mcp[cli]>=1.0.0'"
        )
    mcp = FastMCP(
        name,
        instructions=f"AI Recruitment MCP server: {name} v{server_version}",
    )
    for entry in tool_entries:
        _register_one_tool(mcp, entry)
    return mcp


async def run_stdio_server(
    name: str,
    tool_entries: list[dict],
    *,
    server_version: str = "1.0.0",
) -> None:
    """启动 stdio MCP server（阻塞直到 EOF）。"""
    mcp = build_mcp_server(name, tool_entries, server_version=server_version)
    await mcp.run_stdio_async()


def entrypoint(
    name: str,
    *,
    capability: str = "read",
    version: str = "1.0.0",
):
    """装饰器：把一个返回 (tools_list, handlers_dict) 的函数变成 MCP server 入口。

    用法：
        @entrypoint("mcp-utils", capability="read", version="1.0.0")
        def main():
            return tools_list, handlers_dict
    """
    def decorator(func: Callable) -> Callable:
        async def async_main() -> None:
            tools_list, handlers_dict = func()
            entries = _entries_from_openai_tools(
                tools_list, handlers_dict, capability=capability, version=version
            )
            await run_stdio_server(name, entries, server_version=version)

        def sync_main() -> None:
            asyncio.run(async_main())

        return sync_main

    return decorator


def _entries_from_openai_tools(
    tools: list[dict],
    handlers: dict,
    *,
    capability: str,
    version: str,
) -> list[dict]:
    """OpenAI function-calling 格式 → tool_entries。

    优先从 metadata 读 input_model（V-3 Pydantic 强校验），fallback 从 schema 推导。
    """
    from app.tools.metadata import get_input_model  # 延迟导入避免循环

    entries: list[dict] = []
    for tool in tools:
        fn = tool["function"]
        tool_name = fn["name"]
        handler = handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Tool {tool_name} has schema but no handler")
        # 优先 metadata 里的显式 InputModel（如 CalculateInput 带 pattern 校验）
        input_model = get_input_model(tool_name)
        entries.append(
            {
                "name": tool_name,
                "schema": fn,
                "handler": handler,
                "input_model": input_model,
                "capability": capability,
                "version": version,
            }
        )
    return entries
