"""OperationService — 统一 Agent 操作记录 + 状态机 + SSE 广播。

三层结构：
  1. OperationLog: DB 持久化（每次 Agent 操作记录一条）
  2. OperationStateMachine: 状态流转 (pending→running→completed/failed)
  3. OperationEventBus: 内存事件总线 → SSE 广播到前端
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.operation_log import OperationLog, OperationStatus, ErrorCategory

logger = logging.getLogger(__name__)

SubscriberFn = Callable[[dict], None]


class OperationEventBus:
    """内存事件总线 — Agent 操作事件 → 订阅者（SSE/WebSocket 连接）。

    pub/sub 模式:
      - publish(event) → 推送给所有订阅者
      - subscribe(fn) → 注册回调，返回取消函数
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[SubscriberFn]] = {}

    def subscribe(self, event_type: str, fn: SubscriberFn) -> Callable:
        self._subscribers.setdefault(event_type, []).append(fn)

        def unsubscribe():
            self._subscribers[event_type] = [f for f in self._subscribers[event_type] if f is not fn]

        return unsubscribe

    def publish(self, event_type: str, data: dict) -> None:
        for fn in self._subscribers.get(event_type, []):
            try:
                fn(data)
            except Exception as e:
                logger.warning("EventBus subscriber error: %s", e)


event_bus = OperationEventBus()


class OperationService:
    """统一 Agent 操作记录 + 状态机 + 事件广播。"""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ── 操作日志 CRUD ──

    async def create(
        self,
        user_id: str = "",
        agent_name: str = "",
        action: str = "",
        input_summary: str = "",
        error_category: str = "",
        metadata_json: dict | None = None,
    ) -> OperationLog:
        op = OperationLog(
            id=str(uuid.uuid4()),
            user_id=user_id or None,
            agent_name=agent_name,
            action=action,
            status=OperationStatus.PENDING,
            input_summary=input_summary,
            error_category=error_category or None,
            metadata_json=metadata_json or {},
            immutable=False,
        )
        if self.db:
            self.db.add(op)
            await self.db.commit()
            await self.db.refresh(op)
            op.immutable = True
            await self.db.commit()

        event_bus.publish("operation.created", {
            "operation_id": op.id,
            "agent_name": op.agent_name,
            "action": op.action,
            "status": op.status.value,
            "timestamp": op.created_at.isoformat() if op.created_at else "",
        })
        return op

    async def transition(
        self,
        operation_id: str,
        new_status: OperationStatus,
        output_summary: str = "",
        error_message: str = "",
        error_category: str = "",
    ) -> OperationLog | None:
        if not self.db:
            return None
        stmt = select(OperationLog).where(OperationLog.id == operation_id)
        result = await self.db.execute(stmt)
        op = result.scalar_one_or_none()
        if not op:
            return None
        if op.immutable:
            logger.warning("Attempt to modify immutable operation %s", operation_id)
            return op

        op.status = new_status
        if output_summary:
            op.output_summary = output_summary
        if error_message:
            op.error_message = error_message
        if error_category:
            op.error_category = error_category
        if new_status in (OperationStatus.COMPLETED, OperationStatus.FAILED):
            op.duration_ms = (datetime.now(timezone.utc) - op.created_at).total_seconds() * 1000
        op.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(op)

        event_bus.publish("operation.updated", {
            "operation_id": op.id,
            "agent_name": op.agent_name,
            "action": op.action,
            "status": op.status.value,
            "error_category": op.error_category or "",
            "output_summary": op.output_summary or "",
            "error_message": op.error_message or "",
            "duration_ms": op.duration_ms,
            "timestamp": op.updated_at.isoformat() if op.updated_at else "",
        })
        return op

    async def list(
        self,
        user_id: str | None = None,
        agent_name: str | None = None,
        status: str | None = None,
        error_category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[OperationLog], int]:
        if not self.db:
            return [], 0
        stmt = select(OperationLog)
        count_stmt = select(OperationLog.id)
        if user_id:
            stmt = stmt.where(OperationLog.user_id == user_id)
            count_stmt = count_stmt.where(OperationLog.user_id == user_id)
        if agent_name:
            stmt = stmt.where(OperationLog.agent_name == agent_name)
            count_stmt = count_stmt.where(OperationLog.agent_name == agent_name)
        if status:
            stmt = stmt.where(OperationLog.status == OperationStatus(status))
            count_stmt = count_stmt.where(OperationLog.status == OperationStatus(status))
        if error_category:
            stmt = stmt.where(OperationLog.error_category == error_category)
            count_stmt = count_stmt.where(OperationLog.error_category == error_category)

        count_result = await self.db.execute(count_stmt)
        total = len(list(count_result.scalars().all()))

        stmt = stmt.order_by(desc(OperationLog.created_at)).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    # ── 快捷包装: 运行 Agent 并自动记录 ──

    async def run_and_record(
        self,
        user_id: str,
        agent_name: str,
        action: str,
        input_summary: str,
        metadata_json: dict | None = None,
    ) -> tuple[OperationLog | None, dict | None]:
        """创建操作记录，返回 (operation, None) — 调用方完成后需手动调用 complete/fail。"""
        op = await self.create(
            user_id=user_id, agent_name=agent_name, action=action,
            input_summary=input_summary, metadata_json=metadata_json,
        )
        if op:
            await self.transition(op.id, OperationStatus.RUNNING)
        return op, None

    async def complete(self, operation_id: str, output_summary: str = "") -> None:
        await self.transition(operation_id, OperationStatus.COMPLETED, output_summary=output_summary)

    async def fail(self, operation_id: str, error_message: str = "", error_category: str = "") -> None:
        await self.transition(operation_id, OperationStatus.FAILED, error_message=error_message, error_category=error_category)

    # ── SSE 流生成器 ──

    async def sse_generator(self, user_id: str | None = None):
        """SSE 事件生成器 — 订阅 event_bus 并推送相关事件。"""
        queue: asyncio.Queue[dict] = asyncio.Queue()

        def on_event(data: dict):
            if user_id and data.get("user_id") and data["user_id"] != user_id:
                return
            queue.put_nowait(data)

        unsub_created = event_bus.subscribe("operation.created", on_event)
        unsub_updated = event_bus.subscribe("operation.updated", on_event)

        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    from app.core.sse import sse_event
                    yield sse_event("operation", data)
                except asyncio.TimeoutError:
                    from app.core.sse import sse_event
                    yield sse_event("heartbeat", {"ts": datetime.now(timezone.utc).isoformat()})
        finally:
            unsub_created()
            unsub_updated()
