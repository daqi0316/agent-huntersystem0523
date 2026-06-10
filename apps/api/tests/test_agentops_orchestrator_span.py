"""P1 orchestrator span 测试：chat_with_tools orchestrator_graph 的 span 生命周期。

验证点：
  1. 正常分发时 record_event(SPAN_STARTED) + record_event(SPAN_COMPLETED)
  2. orchestrator 异常时 record_event(SPAN_STARTED) + record_event(SPAN_FAILED)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agentops.core.schemas import EventType

pytestmark = pytest.mark.asyncio


class SpyProvider:
    """记录所有 provider 调用的 spy."""

    def __init__(self):
        self.started_trace = None
        self.recorded_events = []

    async def start_trace(self, event) -> None:
        self.started_trace = event

    async def record_event(self, event) -> None:
        self.recorded_events.append(event)

    async def start_span(self, event) -> None:
        self.recorded_events.append(event)

    async def record_generation(self, event) -> None:
        pass

    async def record_tool_call(self, event) -> None:
        pass

    async def record_score(self, event) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


async def test_orchestrator_span_completed_on_dispatch(monkeypatch) -> None:
    """orchestrator 正常分发 → SPAN_STARTED + SPAN_COMPLETED."""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "intent": "search",
        "status": "completed",
        "agent_result": {"summary": "Search complete"},
    }
    monkeypatch.setattr(
        "app.graphs.orchestrator_graph.create_orchestrator_graph",
        lambda **kw: mock_graph,
    )
    monkeypatch.setattr(
        "app.graphs.orchestrator_graph.make_initial_orchestrator_state",
        lambda **kw: {},
    )

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "search for candidates"}],
        user_id="user-1",
        session_id="session-1",
    )

    # start_trace 正常
    assert spy.started_trace is not None

    # SPAN_STARTED
    span_started = [e for e in spy.recorded_events if e.event_type == EventType.SPAN_STARTED]
    assert len(span_started) == 1
    ss = span_started[0]
    assert ss.name == "orchestrator"
    assert ss.trace_id == spy.started_trace.trace_id
    assert ss.session_id == "session-1"
    assert ss.user_id == "user-1"

    # SPAN_COMPLETED
    span_completed = [e for e in spy.recorded_events if e.event_type == EventType.SPAN_COMPLETED]
    assert len(span_completed) == 1
    sc = span_completed[0]
    assert sc.name == "orchestrator"
    assert sc.trace_id == ss.trace_id
    assert sc.duration_ms is not None and sc.duration_ms >= 0
    assert sc.output is not None
    assert sc.output.get("status") == "completed"

    # 正常返回
    assert result["reply"]


async def test_orchestrator_span_failed_on_graph_exception(monkeypatch) -> None:
    """orchestrator graph 抛出异常 → SPAN_STARTED + SPAN_FAILED + fallback."""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    # graph.ainvoke 抛异常
    mock_graph = AsyncMock()
    mock_graph.ainvoke.side_effect = RuntimeError("graph crash")
    monkeypatch.setattr(
        "app.graphs.orchestrator_graph.create_orchestrator_graph",
        lambda **kw: mock_graph,
    )
    monkeypatch.setattr(
        "app.graphs.orchestrator_graph.make_initial_orchestrator_state",
        lambda **kw: {},
    )

    # LLM fallback 需要 mock
    mock_llm = MagicMock()
    mock_client = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "fallback reply"
    mock_choice.message.tool_calls = None
    mock_choice.message.function_call = None
    mock_client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[mock_choice],
        usage=None,
        model="gpt-4o",
    ))
    mock_llm.client = mock_client
    mock_llm.model = "gpt-4o"
    mock_llm.provider = "test"
    monkeypatch.setattr("app.services.agent_service.get_llm_client", lambda: mock_llm)
    monkeypatch.setattr("app.services.agent_service._get_tools", lambda: [])
    monkeypatch.setattr("app.services.agent_service._get_handlers", lambda: {})

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "search for candidates"}],
        user_id="user-1",
        session_id="session-1",
    )

    # SPAN_STARTED
    span_started = [e for e in spy.recorded_events if e.event_type == EventType.SPAN_STARTED]
    assert len(span_started) == 1
    ss = span_started[0]
    assert ss.name == "orchestrator"

    # SPAN_FAILED
    span_failed = [e for e in spy.recorded_events if e.event_type == EventType.SPAN_FAILED]
    assert len(span_failed) == 1
    sf = span_failed[0]
    assert sf.name == "orchestrator"
    assert sf.trace_id == ss.trace_id
    assert sf.duration_ms is not None and sf.duration_ms >= 0
    assert "graph crash" in sf.error

    # fallback LLM 返回结果
    assert result["reply"] == "fallback reply"
