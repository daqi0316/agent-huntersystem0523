from __future__ import annotations

from app.agentops.core.schemas import (
    BaseEvent,
    LLMGenerationEvent,
    ScoreEvent,
    SpanEvent,
    ToolInvocationEvent,
    TraceEvent,
)


class NoopProvider:
    async def record_event(self, event: BaseEvent) -> None:
        _ = event
        return None

    async def start_trace(self, event: TraceEvent) -> None:
        _ = event
        return None

    async def start_span(self, event: SpanEvent) -> None:
        _ = event
        return None

    async def record_generation(self, event: LLMGenerationEvent) -> None:
        _ = event
        return None

    async def record_tool_call(self, event: ToolInvocationEvent) -> None:
        _ = event
        return None

    async def record_score(self, event: ScoreEvent) -> None:
        _ = event
        return None

    async def flush(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None
