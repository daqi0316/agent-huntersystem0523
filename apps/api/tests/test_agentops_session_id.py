"""P1-5 session_id 贯通测试：全链路所有 trace 事件携带正确的 session_id。

验证点：
  1. TRACE_STARTED: session_id 与输入一致
  2. SPAN_STARTED/COMPLETED/FAILED: session_id 贯通
  3. LLM_GENERATION_STARTED/COMPLETED/FAILED: session_id 贯通
  4. TOOL_INVOCATION_STARTED/COMPLETED/FAILED: session_id 贯通
  5. TRACE_COMPLETED/FAILED: session_id 贯通
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agentops.core.schemas import EventType

pytestmark = pytest.mark.asyncio


class SpyProvider:
    """追踪所有 provider 调用的事件。"""

    def __init__(self):
        self.started_trace = None
        self.recorded_events: list = []
        self.generation_events: list = []
        self.tool_call_events: list = []
        self.span_events: list = []

    async def start_trace(self, event) -> None:
        self.started_trace = event

    async def record_event(self, event) -> None:
        self.recorded_events.append(event)
        if hasattr(event, "event_type") and "span" in (event.event_type or ""):
            self.span_events.append(event)

    async def start_span(self, event) -> None:
        self.span_events.append(event)
        self.recorded_events.append(event)

    async def record_generation(self, event) -> None:
        self.generation_events.append(event)

    async def record_tool_call(self, event) -> None:
        self.tool_call_events.append(event)

    async def record_score(self, event) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


# ── 测试辅助 ──


def _make_usage(prompt: int = 10, completion: int = 20) -> MagicMock:
    u = MagicMock()
    u.prompt_tokens = prompt
    u.completion_tokens = completion
    u.total_tokens = prompt + completion
    return u


def _make_llm_response(content: str = "Hello!", model: str = "test-model") -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = None
    resp = MagicMock()
    resp.model = model
    resp.usage = _make_usage()
    resp.choices = [choice]
    return resp


def _make_tool_call_response(
    tool_name: str = "get_current_time",
    tool_args: str = "{}",
    model: str = "test-model",
) -> MagicMock:
    tc = MagicMock()
    tc.id = "call_1"
    tc.type = "function"
    tc.function.name = tool_name
    tc.function.arguments = tool_args
    choice = MagicMock()
    choice.message.content = None
    choice.message.tool_calls = [tc]
    resp = MagicMock()
    resp.model = model
    resp.usage = _make_usage(prompt=15, completion=5)
    resp.choices = [choice]
    return resp


async def _mock_orch_fallback(monkeypatch) -> None:
    """让 orchestrator_graph 抛异常，走 LLM 回退。"""
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(side_effect=Exception("fallback"))
    monkeypatch.setattr(
        "app.graphs.orchestrator_graph.create_orchestrator_graph",
        MagicMock(return_value=mock_graph),
    )
    monkeypatch.setattr(
        "app.graphs.orchestrator_graph.make_initial_orchestrator_state",
        MagicMock(return_value={}),
    )


async def _mock_context_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.qdrant.get_qdrant",
        AsyncMock(side_effect=Exception("no qdrant")),
    )


# ── 测试 ──


async def test_session_id_flow_on_success(monkeypatch) -> None:
    """全链路成功路径：所有事件携带正确的 session_id。

    路径: orchestrator(fallback) → LLM(started/completed)
        → LLM(tool) → tool(started/completed) → LLM(started/completed) → TRACE_COMPLETED
    """
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orch_fallback(monkeypatch)

    # LLM 两次: 第一次返回 tool_call, 第二次返回最终回复
    resp1 = _make_tool_call_response()
    resp2 = _make_llm_response(content="Final answer")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])
    mock_llm = MagicMock()
    mock_llm.client = mock_client
    mock_llm.model = "test-model"
    monkeypatch.setattr("app.services.agent_service.get_llm_client", lambda: mock_llm)
    monkeypatch.setattr(
        "app.services.agent_service._get_tools",
        lambda: [{"function": {"name": "get_current_time", "description": "Time"}}],
    )
    monkeypatch.setattr(
        "app.services.agent_service._get_handlers",
        lambda: {"get_current_time": MagicMock(return_value={"time": "12:00"})},
    )
    await _mock_context_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    sid = "session-42"

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "what time is it"}],
        user_id="user-1",
        session_id=sid,
    )

    trace_id = spy.started_trace.trace_id
    assert trace_id

    # ── 1. TRACE_STARTED ──
    assert spy.started_trace.session_id == sid
    assert spy.started_trace.input.get("session_id") == sid

    # ── 2. SPAN_STARTED + SPAN_FAILED (orchestrator 失败) ──
    span_started = [e for e in spy.span_events if e.event_type == EventType.SPAN_STARTED]
    assert len(span_started) >= 1
    for e in span_started:
        assert e.session_id == sid

    span_failed = [e for e in spy.span_events if e.event_type == EventType.SPAN_FAILED]
    if span_failed:
        for e in span_failed:
            assert e.session_id == sid

    # ── 3. LLM 事件 ──
    llm_started = [e for e in spy.generation_events if e.event_type == EventType.LLM_GENERATION_STARTED]
    assert len(llm_started) >= 1
    for e in llm_started:
        assert e.session_id == sid
        assert e.trace_id == trace_id

    llm_completed = [e for e in spy.generation_events if e.event_type == EventType.LLM_GENERATION_COMPLETED]
    assert len(llm_completed) >= 1
    for e in llm_completed:
        assert e.session_id == sid
        assert e.trace_id == trace_id

    # ── 4. 工具调用事件 ──
    tool_started = [e for e in spy.tool_call_events if e.event_type == EventType.TOOL_INVOCATION_STARTED]
    assert len(tool_started) >= 1
    for e in tool_started:
        assert e.session_id == sid
        assert e.trace_id == trace_id

    tool_completed = [e for e in spy.tool_call_events if e.event_type == EventType.TOOL_INVOCATION_COMPLETED]
    assert len(tool_completed) >= 1
    for e in tool_completed:
        assert e.session_id == sid
        assert e.trace_id == trace_id

    # ── 5. TRACE_COMPLETED ──
    trace_completed = [e for e in spy.recorded_events if e.event_type == EventType.TRACE_COMPLETED]
    assert len(trace_completed) == 1
    assert trace_completed[0].session_id == sid
    assert trace_completed[0].trace_id == trace_id

    # 正常返回
    assert result["reply"] == "Final answer"


async def test_session_id_flow_on_trace_failure(monkeypatch) -> None:
    """异常路径 TRACE_FAILED 也携带 session_id。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    # command 路径抛异常
    mock_registry = MagicMock()
    mock_executor = AsyncMock()
    mock_executor.execute.side_effect = RuntimeError("cmd boom")
    monkeypatch.setattr(
        "app.services.agent_service.get_default_registry", lambda: mock_registry
    )
    monkeypatch.setattr(
        "app.services.agent_service.CommandExecutor",
        lambda registry=None: mock_executor,
    )

    from app.services.agent_service import chat_with_tools

    sid2 = "session-fail-1"

    with pytest.raises(RuntimeError, match="cmd boom"):
        await chat_with_tools(
            messages=[{"role": "user", "content": "/boom"}],
            user_id="user-1",
            session_id=sid2,
        )

    # TRACE_STARTED
    assert spy.started_trace is not None
    assert spy.started_trace.session_id == sid2

    # TRACE_FAILED
    failed = [e for e in spy.recorded_events if e.event_type == EventType.TRACE_FAILED]
    assert len(failed) == 1
    assert failed[0].session_id == sid2
    assert failed[0].trace_id == spy.started_trace.trace_id


async def test_session_id_with_empty_session(monkeypatch) -> None:
    """空 session_id 时，trace 事件不崩且 session_id 为空字符串。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orch_fallback(monkeypatch)

    resp = _make_llm_response(content="ok")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=resp)
    mock_llm = MagicMock()
    mock_llm.client = mock_client
    mock_llm.model = "test-model"
    monkeypatch.setattr("app.services.agent_service.get_llm_client", lambda: mock_llm)
    monkeypatch.setattr("app.services.agent_service._get_tools", lambda: [])
    monkeypatch.setattr("app.services.agent_service._get_handlers", lambda: {})
    await _mock_context_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "hello"}],
        user_id="user-1",
        session_id=None,
    )

    # session_id 为空字符串时事件不崩
    assert spy.started_trace is not None
    # session_id 可能是 None 或 ""
    # 重点是事件能正常发出
    completed = [e for e in spy.generation_events if e.event_type == EventType.LLM_GENERATION_COMPLETED]
    assert len(completed) >= 1
    assert result["reply"] == "ok"
