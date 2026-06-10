"""P1 主线 smoke test：trace_llm_generation + trace_id + save_conversation_turn span。

验证点：
  1. trace_llm_generation context manager 正确记录 STARTED / COMPLETED / FAILED
  2. chat_with_tools 4 个 return 路径都包含 trace_id
  3. _save_conversation_turn 被 agent_span 包裹
  4. _trace_completed output 包含 trace_id
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agentops.core.schemas import EventType

pytestmark = pytest.mark.asyncio


class SpyProvider:
    """Spy 追踪所有 provider 调用，包括 generation_events 和 span_events。"""

    def __init__(self):
        self.started_trace = None
        self.recorded_events = []
        self.generation_events = []
        self.span_events = []
        self.tool_call_events = []

    async def start_trace(self, event) -> None:
        self.started_trace = event

    async def record_event(self, event) -> None:
        self.recorded_events.append(event)

    async def record_generation(self, event) -> None:
        self.generation_events.append(event)

    async def start_span(self, event) -> None:
        self.span_events.append(event)

    async def record_tool_call(self, event) -> None:
        self.tool_call_events.append(event)

    async def record_score(self, event) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


# ── trace_llm_generation 单元测试 ──


async def test_trace_llm_generation_success(monkeypatch) -> None:
    """trace_llm_generation 记录 STARTED + COMPLETED 事件。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.agentops.runtime.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.llm_generation.get_agentops_provider", lambda: spy)

    from app.agentops.tracing.llm_generation import trace_llm_generation

    async with trace_llm_generation(
        model="test-model",
        provider="test",
        input={"messages": [{"role": "user", "content": "hi"}]},
        parameters={"temperature": 0.1},
    ) as span:
        span.set_output({"content": "hello"})

    # STARTED
    started = [e for e in spy.generation_events if e.event_type == EventType.LLM_GENERATION_STARTED]
    assert len(started) == 1
    s = started[0]
    assert s.model == "test-model"
    assert s.provider == "test"
    assert s.parameters == {"temperature": 0.1}
    assert isinstance(s.input, dict)

    # COMPLETED
    completed = [e for e in spy.generation_events if e.event_type == EventType.LLM_GENERATION_COMPLETED]
    assert len(completed) == 1
    c = completed[0]
    assert c.model == "test-model"
    assert c.duration_ms is not None and c.duration_ms >= 0
    assert c.output == {"content": "hello"}


async def test_trace_llm_generation_failed(monkeypatch) -> None:
    """trace_llm_generation 异常 → FAILED 事件。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.agentops.runtime.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.llm_generation.get_agentops_provider", lambda: spy)

    from app.agentops.tracing.llm_generation import trace_llm_generation

    with pytest.raises(ValueError, match="llm error"):
        async with trace_llm_generation(model="test-model"):
            raise ValueError("llm error")

    started = [e for e in spy.generation_events if e.event_type == EventType.LLM_GENERATION_STARTED]
    assert len(started) == 1

    failed = [e for e in spy.generation_events if e.event_type == EventType.LLM_GENERATION_FAILED]
    assert len(failed) == 1
    f = failed[0]
    assert "llm error" in f.error
    assert f.duration_ms is not None and f.duration_ms >= 0


async def test_trace_llm_generation_with_usage(monkeypatch) -> None:
    """trace_llm_generation 支持 set_usage() 记录 token 用量。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.agentops.runtime.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.llm_generation.get_agentops_provider", lambda: spy)

    from app.agentops.tracing.llm_generation import trace_llm_generation

    usage = MagicMock()
    usage.prompt_tokens = 50
    usage.completion_tokens = 100
    usage.total_tokens = 150

    async with trace_llm_generation(model="test-model") as span:
        span.set_usage(usage)
        span.set_output({"content": "done"})

    completed = [e for e in spy.generation_events if e.event_type == EventType.LLM_GENERATION_COMPLETED]
    assert len(completed) == 1
    c = completed[0]
    assert c.prompt_tokens == 50
    assert c.completion_tokens == 100
    assert c.total_tokens == 150
    assert c.output == {"content": "done"}


# ── trace_id 在 response 中 ──


def _make_command_result(message: str) -> MagicMock:
    r = MagicMock()
    r.action = "executed"
    r.message = message
    return r


async def test_response_contains_trace_id_command(monkeypatch) -> None:
    """命令路径的返回包含 trace_id。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    mock_registry = MagicMock()
    mock_executor = AsyncMock()
    mock_executor.execute.return_value = _make_command_result("done")
    monkeypatch.setattr("app.services.agent_service.get_default_registry", lambda: mock_registry)
    monkeypatch.setattr("app.services.agent_service.CommandExecutor", lambda registry=None: mock_executor)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "/help"}],
        user_id="user-1",
        session_id="session-1",
    )

    assert "trace_id" in result
    assert result["trace_id"] == spy.started_trace.trace_id


async def test_response_contains_trace_id_orchestrator(monkeypatch) -> None:
    """orchestrator 成功路径的返回包含 trace_id。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "intent": "search",
        "status": "completed",
        "agent_result": {"summary": "done"},
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
        messages=[{"role": "user", "content": "search for me"}],
        user_id="user-1",
        session_id="session-1",
    )

    assert "trace_id" in result
    assert result["trace_id"] == spy.started_trace.trace_id


async def test_response_contains_trace_id_llm_loop(monkeypatch) -> None:
    """LLM 工具循环路径的返回包含 trace_id。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    # orchestrator 走 fallback → LLM loop
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

    # mock LLM
    choice = MagicMock()
    choice.message.content = "llm reply"
    choice.message.tool_calls = None
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[choice], usage=None, model="test-model",
    ))
    mock_llm = MagicMock()
    mock_llm.client = mock_client
    mock_llm.model = "test-model"
    monkeypatch.setattr("app.services.agent_service.get_llm_client", lambda: mock_llm)
    monkeypatch.setattr("app.services.agent_service._get_tools", lambda: [])
    monkeypatch.setattr("app.services.agent_service._get_handlers", lambda: {})
    monkeypatch.setattr(
        "app.core.qdrant.get_qdrant",
        AsyncMock(side_effect=Exception("no qdrant")),
    )

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "hello"}],
        user_id="user-1",
        session_id="session-1",
    )

    assert "trace_id" in result
    assert result["trace_id"] == spy.started_trace.trace_id


# ── _trace_completed output 含 trace_id ──


async def test_trace_completed_output_has_trace_id(monkeypatch) -> None:
    """TRACE_COMPLETED 的 output 包含 trace_id。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    mock_registry = MagicMock()
    mock_executor = AsyncMock()
    mock_executor.execute.return_value = _make_command_result("done")
    monkeypatch.setattr("app.services.agent_service.get_default_registry", lambda: mock_registry)
    monkeypatch.setattr("app.services.agent_service.CommandExecutor", lambda registry=None: mock_executor)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "/help"}],
        user_id="user-1",
        session_id="session-1",
    )

    completed = [e for e in spy.recorded_events if e.event_type == EventType.TRACE_COMPLETED]
    assert len(completed) == 1
    output = completed[0].output
    assert isinstance(output, dict)
    assert "trace_id" in output
    assert output["trace_id"] == spy.started_trace.trace_id


# ── save_conversation_turn span ──


async def test_save_conversation_turn_span_recorded(monkeypatch) -> None:
    """_save_conversation_turn 被 agent_span 包裹，记录 save_conversation_turn span。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.get_agentops_provider", lambda: spy)  # agent_span 需要的
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    # orchestrator fallback → LLM loop 路径，会调 _save_conversation_turn
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

    choice = MagicMock()
    choice.message.content = "llm reply"
    choice.message.tool_calls = None
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[choice], usage=None, model="test-model",
    ))
    mock_llm = MagicMock()
    mock_llm.client = mock_client
    mock_llm.model = "test-model"
    monkeypatch.setattr("app.services.agent_service.get_llm_client", lambda: mock_llm)
    monkeypatch.setattr("app.services.agent_service._get_tools", lambda: [])
    monkeypatch.setattr("app.services.agent_service._get_handlers", lambda: {})
    monkeypatch.setattr(
        "app.core.qdrant.get_qdrant",
        AsyncMock(side_effect=Exception("no qdrant")),
    )

    from app.services.agent_service import chat_with_tools

    await chat_with_tools(
        messages=[{"role": "user", "content": "hello"}],
        user_id="user-1",
        session_id="session-1",
    )

    # 查找 save_conversation_turn span
    save_span = [e for e in spy.span_events if getattr(e, "name", "") == "save_conversation_turn"]
    assert len(save_span) >= 1  # LLM loop 路径调一次 _save_conversation_turn
    # 验证 span 携带正确 trace_id
    for sp in save_span:
        assert sp.trace_id == spy.started_trace.trace_id
        assert sp.session_id == "session-1"
        assert sp.user_id == "user-1"
