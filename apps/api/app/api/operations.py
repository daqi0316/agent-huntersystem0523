"""Operations API — 统一 Agent 操作记录 + SSE 实时推送 + WebSocket。

GET    /operations           — 操作记录列表（分页，可按 agent/status 过滤）
GET    /operations/{id}      — 单条操作详情
GET    /operations/stream    — SSE 实时操作流
WS     /operations/ws        — WebSocket 双向通道
POST   /operations/ws/send   — 通过 WebSocket manager 向 Agent 发送指令
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.core.response import success, error
from app.core.sse import sse_headers
from app.services.operation_service import OperationService, event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


class WebSocketManager:
    """管理所有 WebSocket 连接，支持广播和点对点消息。"""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: str, ws: WebSocket) -> None:
        self._connections.setdefault(user_id, [])
        self._connections[user_id] = [c for c in self._connections[user_id] if c is not c]

    async def broadcast(self, event_type: str, data: dict) -> None:
        payload = json.dumps({"event": event_type, "data": data}, ensure_ascii=False)
        for conns in self._connections.values():
            for ws in conns:
                try:
                    await ws.send_text(payload)
                except Exception:
                    pass

    async def send_to_user(self, user_id: str, event_type: str, data: dict) -> None:
        payload = json.dumps({"event": event_type, "data": data}, ensure_ascii=False)
        for ws in self._connections.get(user_id, []):
            try:
                await ws.send_text(payload)
            except Exception:
                pass


ws_manager = WebSocketManager()


@router.get("")
async def list_operations(
    agent_name: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取 Agent 操作记录列表。"""
    svc = OperationService(db)
    items, total = await svc.list(
        user_id=user_id, agent_name=agent_name, status=status,
        limit=limit, offset=offset,
    )
    return success({
        "items": [
            {
                "id": op.id,
                "agent_name": op.agent_name,
                "action": op.action,
                "status": op.status.value,
                "input_summary": op.input_summary,
                "output_summary": op.output_summary,
                "error_message": op.error_message,
                "duration_ms": op.duration_ms,
                "created_at": op.created_at.isoformat() if op.created_at else "",
                "updated_at": op.updated_at.isoformat() if op.updated_at else "",
            }
            for op in items
        ],
        "total": total,
    })


@router.get("/{operation_id}")
async def get_operation(
    operation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取单条操作详情。"""
    from sqlalchemy import select
    from app.models.operation_log import OperationLog

    result = await db.execute(select(OperationLog).where(OperationLog.id == operation_id))
    op = result.scalar_one_or_none()
    if not op:
        return error("操作记录不存在", status_code=404)
    return success({
        "id": op.id,
        "agent_name": op.agent_name,
        "action": op.action,
        "status": op.status.value,
        "input_summary": op.input_summary,
        "output_summary": op.output_summary,
        "error_message": op.error_message,
        "duration_ms": op.duration_ms,
        "created_at": op.created_at.isoformat() if op.created_at else "",
        "updated_at": op.updated_at.isoformat() if op.updated_at else "",
    })


@router.get("/stream")
async def operation_sse_stream(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """SSE 实时操作流 — 所有 Agent 操作事件实时推送到前端。"""
    svc = OperationService(db)
    return StreamingResponse(
        svc.sse_generator(user_id=user_id),
        media_type="text/event-stream",
        headers=sse_headers(),
    )


@router.websocket("/ws")
async def operation_websocket(ws: WebSocket):
    """WebSocket 双向通道 — 前端可接收实时操作推送，也可发送指令。"""
    user_id = "anonymous"
    try:
        await ws.accept()
        await ws.send_text(json.dumps({"event": "connected", "data": {"message": "WebSocket connected"}}))

        async def forward_to_ws(data: dict):
            await ws.send_text(json.dumps({"event": "operation", "data": data}, ensure_ascii=False))

        unsub_created = event_bus.subscribe("operation.created", forward_to_ws)
        unsub_updated = event_bus.subscribe("operation.updated", forward_to_ws)

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                    msg_type = msg.get("event", "")
                    msg_data = msg.get("data", {})
                    if msg_type == "ping":
                        await ws.send_text(json.dumps({"event": "pong", "data": {}}))
                    elif msg_type == "subscribe":
                        user_id = msg_data.get("user_id", "anonymous")
                        await ws.send_text(json.dumps({"event": "subscribed", "data": {"user_id": user_id}}))
                    else:
                        event_bus.publish(f"ws:{msg_type}", msg_data)
                        await ws.send_text(json.dumps({"event": "ack", "data": {"type": msg_type}}))
                except json.JSONDecodeError:
                    await ws.send_text(json.dumps({"event": "error", "data": {"message": "invalid JSON"}}))
        except WebSocketDisconnect:
            pass
        finally:
            unsub_created()
            unsub_updated()
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
