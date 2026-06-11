"""P2b-1: WebSocket 端点 — 任务实时进度"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.sourcing.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws/sourcing", tags=["sourcing/ws"])


@router.websocket("/tasks/{task_id}")
async def task_progress_ws(ws: WebSocket, task_id: str):
    await ws_manager.connect(task_id, ws)
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"event": "pong", "data": {}}))
    except WebSocketDisconnect:
        ws_manager.disconnect(task_id, ws)
        logger.debug("WS disconnected: task=%s", task_id)
    except Exception as e:
        ws_manager.disconnect(task_id, ws)
        logger.warning("WS error task=%s: %s", task_id, e)
