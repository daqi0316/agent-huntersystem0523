"""MessageBus — 异步事件总线，用于 Agent 间通信。

设计:
- 推模式: Agent publish 事件，订阅者异步收到通知
- 拉模式: Agent 可以查询事件历史
- 类型化的 Event 对象，含 payload、source、timestamp
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
import uuid
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

EventHandler = Callable[["Event"], Coroutine[Any, Any, None]]


class EventType(str, enum.Enum):
    SCREENING_COMPLETED = "screening.completed"
    INTERVIEW_SCHEDULED = "interview.scheduled"
    INTERVIEW_EVALUATED = "interview.evaluated"
    OFFER_SENT = "offer.sent"
    OFFER_ACCEPTED = "offer.accepted"
    OFFER_REJECTED = "offer.rejected"
    CANDIDATE_MOVED = "candidate.moved"
    AGENT_ERROR = "agent.error"
    AGENT_LOG = "agent.log"
    TASK_DELEGATED = "task.delegated"
    TASK_COMPLETED = "task.completed"
    SYSTEM_NOTIFICATION = "system.notification"


class Event:
    """不可变事件对象。"""

    def __init__(
        self,
        type: EventType,
        payload: dict[str, Any],
        source: str = "",
        aggregate_id: str | None = None,
    ) -> None:
        self.id: str = str(uuid.uuid4())
        self.type: EventType = type
        self.payload: dict[str, Any] = payload
        self.source: str = source
        self.aggregate_id: str | None = aggregate_id
        self.timestamp: float = time.time()

    def __repr__(self) -> str:
        return (
            f"Event(id={self.id[:8]}, type={self.type.value}, "
            f"source={self.source}, aggregate_id={self.aggregate_id})"
        )


class MessageBus:
    """进程内异步事件总线。

    用法:
        bus = MessageBus()

        async def on_screened(event: Event):
            print(f"Screening done: {event.payload}")

        await bus.subscribe(EventType.SCREENING_COMPLETED, on_screened)
        await bus.publish(EventType.SCREENING_COMPLETED, {"candidate_id": "c-123"})
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._history: list[Event] = []
        self._max_history = max_history
        self._lock = asyncio.Lock()

    # ── Publish ──

    async def publish(
        self,
        type: EventType,
        payload: dict[str, Any],
        source: str = "",
        aggregate_id: str | None = None,
    ) -> Event:
        """发布事件到所有订阅者。"""
        event = Event(
            type=type,
            payload=payload,
            source=source,
            aggregate_id=aggregate_id,
        )

        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        handlers = self._subscribers.get(type, []) + self._subscribers.get(EventType.SYSTEM_NOTIFICATION, [])
        if not handlers:
            logger.debug("MessageBus: no subscribers for %s", type.value)
            return event

        results = await asyncio.gather(
            *[h(event) for h in handlers],
            return_exceptions=True,
        )
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error("MessageBus: handler %d failed for %s: %s", i, type.value, r)

        return event

    # ── Subscribe ──

    async def subscribe(self, type: EventType, handler: EventHandler) -> None:
        """订阅指定事件类型。"""
        async with self._lock:
            if type not in self._subscribers:
                self._subscribers[type] = []
            self._subscribers[type].append(handler)
            logger.debug("MessageBus: subscribed to %s (total %d)", type.value, len(self._subscribers[type]))

    async def unsubscribe(self, type: EventType, handler: EventHandler) -> bool:
        """取消订阅。"""
        async with self._lock:
            if type not in self._subscribers:
                return False
            try:
                self._subscribers[type].remove(handler)
                return True
            except ValueError:
                return False

    # ── History ──

    def history(
        self,
        type: EventType | None = None,
        source: str | None = None,
        aggregate_id: str | None = None,
        limit: int = 50,
    ) -> list[Event]:
        """查询事件历史。"""
        events = self._history
        if type:
            events = [e for e in events if e.type == type]
        if source:
            events = [e for e in events if e.source == source]
        if aggregate_id:
            events = [e for e in events if e.aggregate_id == aggregate_id]
        return events[-limit:]

    async def clear_history(self) -> None:
        async with self._lock:
            self._history.clear()

    @property
    def subscriber_count(self) -> int:
        return sum(len(h) for h in self._subscribers.values())


_bus_instance: MessageBus | None = None


def get_message_bus() -> MessageBus:
    """获取全局 MessageBus 单例。"""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = MessageBus()
    return _bus_instance
