from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.agentops.core.schemas import (
    BaseEvent,
    LLMGenerationEvent,
    ScoreEvent,
    SpanEvent,
    ToolInvocationEvent,
    TraceEvent,
)

from .base import AgentOpsProvider

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CompositeProvider:
    providers: list[AgentOpsProvider] = field(default_factory=list)

    async def record_event(self, event: BaseEvent) -> None:
        await self._fan_out(lambda provider: provider.record_event(event))

    async def start_trace(self, event: TraceEvent) -> None:
        await self._fan_out(lambda provider: provider.start_trace(event))

    async def start_span(self, event: SpanEvent) -> None:
        await self._fan_out(lambda provider: provider.start_span(event))

    async def record_generation(self, event: LLMGenerationEvent) -> None:
        await self._fan_out(lambda provider: provider.record_generation(event))

    async def record_tool_call(self, event: ToolInvocationEvent) -> None:
        await self._fan_out(lambda provider: provider.record_tool_call(event))

    async def record_score(self, event: ScoreEvent) -> None:
        await self._fan_out(lambda provider: provider.record_score(event))

    async def flush(self) -> None:
        for provider in self.providers:
            try:
                await provider.flush()
            except Exception as exc:
                logger.warning("agentops provider flush failed: %s", exc)

    async def shutdown(self) -> None:
        for provider in self.providers:
            try:
                await provider.shutdown()
            except Exception as exc:
                logger.warning("agentops provider shutdown failed: %s", exc)

    async def _fan_out(self, call_provider: Callable[[AgentOpsProvider], Awaitable[None]]) -> None:
        for provider in self.providers:
            try:
                await call_provider(provider)
            except Exception as exc:
                logger.warning("agentops provider call failed: %s", exc)
