from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol

from app.agentops.core.schemas import (
    BaseEvent,
    LLMGenerationEvent,
    ScoreEvent,
    SpanEvent,
    ToolInvocationEvent,
    TraceEvent,
)


class QueueLike(Protocol):
    def enqueue(self, event: BaseEvent) -> bool: ...

    def flush(self) -> Awaitable[None]: ...

    def shutdown(self) -> Awaitable[None]: ...


@dataclass(slots=True)
class ExporterProvider:
    queue: QueueLike

    async def record_event(self, event: BaseEvent) -> None:
        self.queue.enqueue(event)

    async def start_trace(self, event: TraceEvent) -> None:
        self.queue.enqueue(event)

    async def start_span(self, event: SpanEvent) -> None:
        self.queue.enqueue(event)

    async def record_generation(self, event: LLMGenerationEvent) -> None:
        self.queue.enqueue(event)

    async def record_tool_call(self, event: ToolInvocationEvent) -> None:
        self.queue.enqueue(event)

    async def record_score(self, event: ScoreEvent) -> None:
        self.queue.enqueue(event)

    async def flush(self) -> None:
        await self.queue.flush()

    async def shutdown(self) -> None:
        await self.queue.shutdown()
