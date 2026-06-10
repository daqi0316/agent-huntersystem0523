from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.agentops.core.schemas import BaseEvent

from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

ExportEvent = Callable[[BaseEvent], Awaitable[None]]


@dataclass(slots=True)
class QueueStats:
    accepted: int = 0
    dropped: int = 0
    exported: int = 0
    failed: int = 0
    circuit_open_drops: int = 0


@dataclass(slots=True)
class AgentOpsQueue:
    exporter: ExportEvent
    max_size: int = 1000
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    stats: QueueStats = field(default_factory=QueueStats)
    _events: list[BaseEvent] = field(default_factory=list)

    def enqueue(self, event: BaseEvent) -> bool:
        if len(self._events) >= self.max_size:
            self.stats.dropped += 1
            return False
        self._events.append(event)
        self.stats.accepted += 1
        return True

    async def flush(self) -> None:
        pending = list(self._events)
        self._events.clear()
        for event in pending:
            if not self.circuit_breaker.allow_request():
                self.stats.circuit_open_drops += 1
                continue
            try:
                await self.exporter(event)
            except Exception as exc:
                self.stats.failed += 1
                self.circuit_breaker.record_failure()
                logger.warning("agentops export failed: %s", exc)
                continue
            self.stats.exported += 1
            self.circuit_breaker.record_success()

    async def shutdown(self) -> None:
        await self.flush()

    def size(self) -> int:
        return len(self._events)

    async def flush_with_timeout(self, timeout_seconds: float) -> None:
        await asyncio.wait_for(self.flush(), timeout=timeout_seconds)
