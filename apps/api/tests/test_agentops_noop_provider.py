import pytest

from app.agentops.core.schemas import LLMGenerationEvent, ScoreEvent, SpanEvent, ToolInvocationEvent, TraceEvent
from app.agentops.providers.noop import NoopProvider

pytestmark = pytest.mark.asyncio


async def test_noop_provider_methods_do_not_raise():
    provider = NoopProvider()

    await provider.start_trace(TraceEvent(name="trace"))
    await provider.start_span(SpanEvent(name="span"))
    await provider.record_generation(LLMGenerationEvent(name="generation"))
    await provider.record_tool_call(ToolInvocationEvent(name="tool", tool_name="get_schedule"))
    await provider.record_score(ScoreEvent(name="score", score_name="quality", value=1))
    await provider.flush()
    await provider.shutdown()
