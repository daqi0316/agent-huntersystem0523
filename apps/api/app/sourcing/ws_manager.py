"""P2b-1: WebSocket 连接管理器 — 任务进度实时推送"""
from __future__ import annotations

import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class TaskProgressManager:
    """按 task_id 管理 WebSocket 连接，推送采集进度"""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, task_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(task_id, []).append(ws)
        logger.debug("WS connected: task=%s, total=%d", task_id, len(self._connections[task_id]))

    def disconnect(self, task_id: str, ws: WebSocket):
        conns = self._connections.get(task_id, [])
        self._connections[task_id] = [c for c in conns if c is not ws]
        if not self._connections[task_id]:
            self._connections.pop(task_id, None)

    async def push_progress(self, task_id: str, event: str, data: dict):
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
        for ws in self._connections.get(task_id, []):
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(task_id, ws)

    async def broadcast(self, event: str, data: dict):
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
        for task_id in list(self._connections.keys()):
            for ws in self._connections.get(task_id, []):
                try:
                    await ws.send_text(payload)
                except Exception:
                    self.disconnect(task_id, ws)


ws_manager = TaskProgressManager()
