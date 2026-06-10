from typing import override

import pytest

from app.agentops.core.schemas import (
    BaseEvent,
    LLMGenerationEvent,
    ScoreEvent,
    SpanEvent,
    ToolInvocationEvent,
    TraceEvent,
)
from app.agentops.providers.composite import CompositeProvider

pytestmark = pytest.mark.asyncio


class RecordingProvider:
    def __init__(self):
        self.events: list[tuple[str, str]] = []
        self.flushed: bool = False
        self.shutdown_called: bool = False

    async def record_event(self, event: BaseEvent) -> None:
        self.events.append(("record_event", event.name))

    async def start_trace(self, event: TraceEvent) -> None:
        self.events.append(("start_trace", event.name))

    async def start_span(self, event: SpanEvent) -> None:
        self.events.append(("start_span", event.name))

    async def record_generation(self, event: LLMGenerationEvent) -> None:
        self.events.append(("record_generation", event.name))

    async def record_tool_call(self, event: ToolInvocationEvent) -> None:
        self.events.append(("record_tool_call", event.name))

    async def record_score(self, event: ScoreEvent) -> None:
        self.events.append(("record_score", event.name))

    async def flush(self) -> None:
        self.flushed = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


class FailingProvider(RecordingProvider):
    @override
    async def start_trace(self, event: TraceEvent) -> None:
        _ = event
        raise RuntimeError("provider down")

    @override
    async def flush(self) -> None:
        raise RuntimeError("flush down")

    @override
    async def shutdown(self) -> None:
        raise RuntimeError("shutdown down")


async def test_composite_provider_fans_out_and_isolates_failures():
    good = RecordingProvider()
    composite = CompositeProvider(providers=[FailingProvider(), good])

    await composite.start_trace(TraceEvent(name="trace"))
    await composite.flush()
    await composite.shutdown()

    assert good.events == [("start_trace", "trace")]
    assert good.flushed is True
    assert good.shutdown_called is True
