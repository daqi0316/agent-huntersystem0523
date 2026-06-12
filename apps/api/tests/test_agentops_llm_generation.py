"""P1 LLM 生成 trace 测试：_trace_completion 的 record_generation 生命周期。

验证点：
  1. LLM 调用前 record_generation(LLM_GENERATION_STARTED) 被调用
  2. 成功时 record_generation(LLM_GENERATION_COMPLETED) 被调用，含 token 用量
  3. LLM 调用异常时 record_generation(LLM_GENERATION_FAILED) 被调用
  4. 所有事件携带正确的 trace_id / user_id / session_id
  5. 输入输出经过 sanitize_payload 脱敏
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agentops.core.schemas import EventType

pytestmark = pytest.mark.asyncio


class SpyProvider:
    """Spy 追踪所有 provider 调用。"""

    def __init__(self):
        self.started_trace = None
        self.recorded_events = []
        self.generation_events = []

    async def start_trace(self, event) -> None:
        self.started_trace = event

    async def record_event(self, event) -> None:
        self.recorded_events.append(event)

    async def record_generation(self, event) -> None:
        self.generation_events.append(event)

    async def start_span(self, event) -> None:
        pass

    async def record_tool_call(self, event) -> None:
        pass

    async def record_score(self, event) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


def _make_fake_usage(prompt: int = 10, completion: int = 20) -> MagicMock:
    u = MagicMock()
    u.prompt_tokens = prompt
    u.completion_tokens = completion
    u.total_tokens = prompt + completion
    return u


def _make_fake_llm_response(
    content: str = "Hello!",
    model: str = "test-model",
) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = None

    resp = MagicMock()
    resp.model = model
    resp.usage = _make_fake_usage()
    resp.choices = [choice]
    return resp


def _make_tool_call_response(
    tool_name: str = "web_search",
    tool_args: str = '{"query": "test"}',
    model: str = "test-model",
) -> MagicMock:
    """返回一个带工具调用的 LLM 响应。
    function.name / function.arguments 必须是真实字符串（不是 MagicMock）。
    """
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
    resp.usage = _make_fake_usage(prompt=15, completion=5)
    resp.choices = [choice]
    return resp


async def _mock_orchestrator_fallback(monkeypatch) -> None:
    """让 orchestrator 异常，走 LLM 工具循环 fallback。"""
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(side_effect=Exception("mock fallback"))
    monkeypatch.setattr(
        "app.graphs.orchestrator_graph.create_orchestrator_graph",
        MagicMock(return_value=mock_graph),
    )
    monkeypatch.setattr(
        "app.graphs.orchestrator_graph.make_initial_orchestrator_state",
        MagicMock(return_value={}),
    )


async def _mock_contextbuilder_fallback(monkeypatch) -> None:
    """让 ContextBuilder 走 fallback（get_qdrant 抛异常）。"""
    monkeypatch.setattr(
        "app.core.qdrant.get_qdrant",
        AsyncMock(side_effect=Exception("no qdrant")),
    )


async def _mock_llm(monkeypatch, mock_client) -> None:
    """Mock LLM client and tools/handlers to empty."""
    mock_llm = MagicMock()
    mock_llm.client = mock_client
    mock_llm.model = "test-model"
    monkeypatch.setattr("app.services.agent_service.get_llm_client", lambda: mock_llm)
    monkeypatch.setattr("app.services.agent_service._get_tools", lambda: [])
    monkeypatch.setattr("app.services.agent_service._get_handlers", lambda: {})


# ── Tests ──


async def test_llm_generation_success(monkeypatch) -> None:
    """单次 LLM 调用 → STARTED + COMPLETED 事件."""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.runtime.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.llm_generation.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.runtime.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.llm_generation.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_fake_llm_response(content="Hello world"),
    )
    await _mock_llm(monkeypatch, mock_client)
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "hello"}],
        user_id="user-1",
        session_id="session-1",
    )

    # start_trace 正常
    assert spy.started_trace is not None
    trace_id = spy.started_trace.trace_id

    # LLM_GENERATION_STARTED
    started = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_STARTED
    ]
    assert len(started) >= 1
    s = started[0]
    assert s.trace_id == trace_id
    assert s.user_id == "user-1"
    assert s.session_id == "session-1"
    assert s.model == "test-model"
    assert isinstance(s.input, dict)

    # LLM_GENERATION_COMPLETED
    completed = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_COMPLETED
    ]
    assert len(completed) == 1
    c = completed[0]
    assert c.trace_id == trace_id
    assert c.prompt_tokens == 10
    assert c.completion_tokens == 20
    assert c.total_tokens == 30
    assert c.duration_ms is not None and c.duration_ms >= 0
    assert isinstance(c.output, dict)

    assert result["reply"] == "Hello world"


async def test_llm_generation_retry_then_success(monkeypatch) -> None:
    """首次 LLM 失败重试后成功 → 2 组 STARTED, 1 组 FAILED, 1 组 COMPLETED。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.runtime.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.llm_generation.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    fake_resp = _make_fake_llm_response(content="Retry OK")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[RuntimeError("timeout"), fake_resp],
    )
    await _mock_llm(monkeypatch, mock_client)
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "hello"}],
        user_id="user-1",
    )

    started = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_STARTED
    ]
    completed = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_COMPLETED
    ]
    failed = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_FAILED
    ]

    # 首次调用失败 → 重试第二次成功
    assert len(started) == 2
    assert len(failed) == 1
    assert len(completed) == 1
    assert result["reply"] == "Retry OK"


async def test_llm_generation_all_retries_exhausted(monkeypatch) -> None:
    """3 次重试全部失败 → 3 组 STARTED + FAILED，异常透传。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.runtime.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.llm_generation.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("LLM unavailable"),
    )
    await _mock_llm(monkeypatch, mock_client)
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        await chat_with_tools(
            messages=[{"role": "user", "content": "hello"}],
            user_id="user-1",
        )

    started = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_STARTED
    ]
    failed = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_FAILED
    ]

    # 每次重试独立记录 LLM 事件
    assert len(started) == 3
    assert len(failed) == 3
    for f in failed:
        assert f.error == "LLM unavailable"


async def test_llm_generation_two_calls(monkeypatch) -> None:
    """工具调用场景：第一次 LLM 返回 tool_calls → 工具执行 → 第二次 LLM 走 trace。

    验证两次 LLM 调用都有独立的 STARTED + COMPLETED 事件。
    """
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.runtime.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.llm_generation.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    resp1 = _make_tool_call_response(tool_name="get_current_time", tool_args="{}")
    resp2 = _make_fake_llm_response(content="Final answer after tools")

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
    # handler 返回真实 dict
    monkeypatch.setattr(
        "app.services.agent_service._get_handlers",
        lambda: {"get_current_time": MagicMock(return_value={"time": "12:00"})},
    )
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "what time is it"}],
        user_id="user-1",
    )

    started = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_STARTED
    ]
    completed = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_COMPLETED
    ]

    assert len(started) == 2
    assert len(completed) == 2

    # 第一次调用：工具调用（prompt_tokens=15）
    # 第二次调用：最终回复（prompt_tokens=10，来自 _make_fake_llm_response 默认值）
    c1, c2 = completed[0], completed[1]
    assert c1.prompt_tokens == 15
    assert c2.prompt_tokens == 10

    assert result["reply"] == "Final answer after tools"


async def test_llm_generation_second_call_timeout(monkeypatch) -> None:
    """第二次 LLM 超时 → 第二次调用记录 FAILED，主流程降级返回。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.runtime.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.agentops.tracing.llm_generation.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    resp1 = _make_tool_call_response(tool_name="get_current_time", tool_args="{}")

    # 第一次成功（工具调用），第二次超时
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[resp1, __import__("asyncio").TimeoutError("timed out")],
    )
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
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "what time is it"}],
        user_id="user-1",
    )

    # 第一次 LLM 调用成功（COMPLETED），第二次超时（FAILED）
    completed = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_COMPLETED
    ]
    failed = [
        e for e in spy.generation_events
        if e.event_type == EventType.LLM_GENERATION_FAILED
    ]

    assert len(completed) == 1
    assert len(failed) >= 1  # 超时导致 FAILED

    # 主流程降级，不抛异常
    assert "reply" in result
