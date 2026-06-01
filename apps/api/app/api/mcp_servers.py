"""MCP Server 管理 API — CRUD + 连接测试。"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success, error
from app.mcp.client import test_connection
from app.mcp.manager import mcp_manager
from app.models.mcp_server import MCPServer
from app.schemas.mcp_server import (
    MCPTestConnectionRequest,
    MCPTestConnectionResponse,
    MCPServerCreate,
    MCPServerRead,
    MCPServerUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _server_to_read(s: MCPServer) -> dict[str, Any]:
    """MCPServer ORM → 响应 dict（手动处理 tools_cache JSON）。"""
    tools_cache = None
    if s.tools_cache:
        try:
            tools_cache = json.loads(s.tools_cache)
        except (json.JSONDecodeError, TypeError):
            tools_cache = None
    return {
        "id": s.id,
        "name": s.name,
        "server_url": s.server_url,
        "protocol": s.protocol,
        "auth_type": s.auth_type,
        "enabled": s.enabled,
        "tools_cache": tools_cache,
        "last_heartbeat": s.last_heartbeat,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


@router.get("/servers")
async def list_servers(
    db: AsyncSession = Depends(get_db),
):
    """获取所有已配置的 MCP Server。"""
    result = await db.execute(
        select(MCPServer).order_by(MCPServer.created_at.desc())
    )
    servers = result.scalars().all()
    return success([_server_to_read(s) for s in servers])


@router.post("/servers", status_code=201)
async def create_server(
    req: MCPServerCreate,
    db: AsyncSession = Depends(get_db),
):
    """添加一个新的 MCP Server 配置。"""
    server = MCPServer(
        name=req.name,
        server_url=req.server_url,
        protocol=req.protocol,
        auth_type=req.auth_type,
        auth_token=req.auth_token,
        enabled=True,
    )
    # 缓存初始工具列表（非阻塞）
    try:
        conn = await test_connection(server.server_url, server.auth_type, server.auth_token or "")
        if conn["success"]:
            server.tools_cache = json.dumps(conn["tools"], ensure_ascii=False)
    except Exception:
        pass

    db.add(server)
    await db.commit()
    await db.refresh(server)

    # 注册到运行时管理器
    await mcp_manager.register(
        server_id=server.id,
        name=server.name,
        url=server.server_url,
        auth_type=server.auth_type,
        auth_token=server.auth_token or "",
        tools_cache_data=json.loads(server.tools_cache) if server.tools_cache else None,
    )

    return success(_server_to_read(server))


@router.get("/servers/{server_id}")
async def get_server(
    server_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取单个 MCP Server 详情。"""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return error("MCP Server 不存在", status_code=404)
    return success(_server_to_read(server))


@router.put("/servers/{server_id}")
async def update_server(
    server_id: str,
    req: MCPServerUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新 MCP Server 配置。"""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return error("MCP Server 不存在", status_code=404)

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(server, field, value)

    # 如果 URL 或凭证变了，重新发现工具
    if any(f in update_data for f in ("server_url", "auth_type", "auth_token")):
        try:
            conn = await test_connection(
                server.server_url,
                server.auth_type,
                server.auth_token or "",
            )
            if conn["success"]:
                server.tools_cache = json.dumps(conn["tools"], ensure_ascii=False)
        except Exception:
            pass

    await db.commit()
    await db.refresh(server)

    # 更新运行时管理器
    await mcp_manager.register(
        server_id=server.id,
        name=server.name,
        url=server.server_url,
        auth_type=server.auth_type,
        auth_token=server.auth_token or "",
        tools_cache_data=json.loads(server.tools_cache) if server.tools_cache else None,
    )

    return success(_server_to_read(server))


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除 MCP Server 配置。"""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return error("MCP Server 不存在", status_code=404)

    await db.delete(server)
    await db.commit()

    await mcp_manager.unregister(server_id)

    return success({"message": "已删除"})


@router.post("/servers/test")
async def test_server_connection(
    req: MCPTestConnectionRequest,
):
    """测试连接一个 MCP Server（无需保存）。"""
    conn = await test_connection(req.server_url, req.auth_type, req.auth_token or "")
    return MCPTestConnectionResponse(**conn).model_dump()


@router.post("/servers/{server_id}/test")
async def test_existing_server_connection(
    server_id: str,
    db: AsyncSession = Depends(get_db),
):
    """测试已保存的 MCP Server 连接。"""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return error("MCP Server 不存在", status_code=404)

    conn = await test_connection(server.server_url, server.auth_type, server.auth_token or "")
    return MCPTestConnectionResponse(**conn).model_dump()
