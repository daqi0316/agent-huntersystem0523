from __future__ import annotations

from typing import Protocol

from app.agentops.core.schemas import (
    BaseEvent,
    LLMGenerationEvent,
    ScoreEvent,
    SpanEvent,
    ToolInvocationEvent,
    TraceEvent,
)


class AgentOpsProvider(Protocol):
    async def record_event(self, event: BaseEvent) -> None: ...

    async def start_trace(self, event: TraceEvent) -> None: ...

    async def start_span(self, event: SpanEvent) -> None: ...

    async def record_generation(self, event: LLMGenerationEvent) -> None: ...

    async def record_tool_call(self, event: ToolInvocationEvent) -> None: ...

    async def record_score(self, event: ScoreEvent) -> None: ...

    async def flush(self) -> None: ...

    async def shutdown(self) -> None: ...
