"""MCP 管理 API — 暴露工具列表 / server 状态 / 快照。

新增路由（PR-1a）：
  GET /api/v1/mcp/tools              — 列出所有 tool（MCP / OpenAI 格式）
  GET /api/v1/mcp/tools/{name}       — 单个 tool 详情
  GET /api/v1/mcp/servers            — server 状态
  GET /api/v1/mcp/registry/snapshot  — 启动时 dump 的注册表快照

不动现有路由，纯新增。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.mcp.host import mcp_host
from app.mcp.registry import ToolRegistry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mcp", tags=["MCP Host (v3)"])


@router.get("/tools")
async def list_tools(
    format: str = Query("mcp", pattern="^(mcp|openai)$"),
    capability: str | None = Query(None, pattern="^(read|write|destructive|admin)$"),
    include_deprecated: bool = Query(False),
):
    """列出所有 tool schemas。

    Args:
        format: mcp (MCP Tool schema) | openai (OpenAI function-calling)
        capability: 可选过滤
        include_deprecated: 是否包含 deprecated tool
    """
    tools = mcp_host.list_tools(format=format)
    if capability:
        tools = [t for t in tools if (t.get("meta", {}).get("capability") if format == "mcp" else t.get("function", {}).get("capability", "read")) == capability]
    if not include_deprecated:
        if format == "mcp":
            tools = [t for t in tools if not t.get("meta", {}).get("deprecated", False)]
    return {
        "count": len(tools),
        "format": format,
        "tools": tools,
    }


@router.get("/tools/{name}")
async def get_tool(name: str):
    """单个 tool 详情（含 Pydantic InputModel 提示）。"""
    entry = mcp_host.registry.get(name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Tool {name!r} not found")
    from app.tools.metadata import get_input_model
    return {
        "name": entry.name,
        "server_id": entry.server_id,
        "capability": entry.capability,
        "version": entry.version,
        "description": entry.description,
        "input_schema": entry.input_schema,
        "deprecated": entry.deprecated,
        "replacement": entry.replacement,
        "has_pydantic_input_model": get_input_model(name) is not None,
    }


@router.get("/servers")
async def list_servers():
    """server 进程状态。"""
    return {
        "count": len(mcp_host.supervisor.all_servers()),
        "servers": mcp_host.list_servers(),
    }


@router.get("/registry/snapshot")
async def get_registry_snapshot():
    """读启动时 dump 的注册表 JSON（CI 校验 / 文档生成用）。"""
    path = Path("app/mcp_servers/_generated_registry.json")
    if not path.exists():
        return {
            "exists": False,
            "message": "Snapshot not generated. MCP host may not have started yet.",
        }
    return {
        "exists": True,
        "path": str(path),
        "data": json.loads(path.read_text(encoding="utf-8")),
    }
