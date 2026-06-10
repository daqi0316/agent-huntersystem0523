"""P1 工具调用 trace 测试：_trace_tool_call 的 record_tool_call 生命周期。

验证点：
  1. 工具调用前 record_tool_call(TOOL_INVOCATION_STARTED) 被调用
  2. 成功时 record_tool_call(TOOL_INVOCATION_COMPLETED) 被调用，含 duration_ms
  3. 重试后成功 retry_count > 0
  4. 所有重试耗尽后 record_tool_call(TOOL_INVOCATION_FAILED) 被调用
  5. 未知工具依然记录 FAILED
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agentops.core.schemas import EventType
from app.tools.metadata import ToolMetadata

pytestmark = pytest.mark.asyncio


class SpyProvider:
    """Spy 追踪所有 provider 调用，含工具调用事件。"""

    def __init__(self):
        self.started_trace = None
        self.recorded_events = []
        self.generation_events = []
        self.tool_call_events = []

    async def start_trace(self, event) -> None:
        self.started_trace = event

    async def record_event(self, event) -> None:
        self.recorded_events.append(event)

    async def record_generation(self, event) -> None:
        self.generation_events.append(event)

    async def record_tool_call(self, event) -> None:
        self.tool_call_events.append(event)

    async def start_span(self, event) -> None:
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
    resp.usage = _make_fake_usage(prompt=15, completion=5)
    resp.choices = [choice]
    return resp


async def _mock_orchestrator_fallback(monkeypatch) -> None:
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
    monkeypatch.setattr(
        "app.core.qdrant.get_qdrant",
        AsyncMock(side_effect=Exception("no qdrant")),
    )


async def _mock_llm_and_tools(
    monkeypatch,
    mock_client,
    tools: list | None = None,
    handlers: dict | None = None,
) -> None:
    mock_llm = MagicMock()
    mock_llm.client = mock_client
    mock_llm.model = "test-model"
    monkeypatch.setattr("app.services.agent_service.get_llm_client", lambda: mock_llm)
    monkeypatch.setattr(
        "app.services.agent_service._get_tools",
        lambda: tools or [{"function": {"name": "get_current_time", "description": "Time"}}],
    )
    monkeypatch.setattr(
        "app.services.agent_service._get_handlers",
        lambda: handlers or {"get_current_time": MagicMock(return_value={"time": "12:00"})},
    )


def _register_retryable_tool(monkeypatch, tool_name: str, max_retries: int = 2) -> None:
    """在 TOOL_METADATA 中注册一个 retryable 工具。"""
    import app.tools.metadata as md
    monkeypatch.setitem(md.TOOL_METADATA, tool_name, ToolMetadata(retryable=True, max_retries=max_retries))


# ── Tests ──


async def test_tool_invocation_success(monkeypatch) -> None:
    """单次工具调用成功 → STARTED + COMPLETED 事件."""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    resp1 = _make_tool_call_response(tool_name="get_current_time", tool_args="{}")
    resp2 = _make_fake_llm_response(content="Final answer")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])
    await _mock_llm_and_tools(
        monkeypatch,
        mock_client,
        handlers={"get_current_time": MagicMock(return_value={"time": "12:00"})},
    )
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "what time is it"}],
        user_id="user-1",
        session_id="session-1",
    )

    trace_id = spy.started_trace.trace_id

    # TOOL_INVOCATION_STARTED
    started = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_STARTED
    ]
    assert len(started) == 1
    s = started[0]
    assert s.trace_id == trace_id
    assert s.user_id == "user-1"
    assert s.session_id == "session-1"
    assert s.tool_name == "get_current_time"
    assert s.tool_category == "read"  # ToolMetadata().capability 默认值

    # TOOL_INVOCATION_COMPLETED
    completed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_COMPLETED
    ]
    assert len(completed) == 1
    c = completed[0]
    assert c.trace_id == trace_id
    assert c.tool_name == "get_current_time"
    assert c.success is True
    assert c.retry_count == 0
    assert c.duration_ms is not None and c.duration_ms >= 0
    assert isinstance(c.output, dict)

    # 没有 FAILED 事件
    failed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_FAILED
    ]
    assert len(failed) == 0

    assert result["reply"] == "Final answer"


async def test_tool_invocation_not_retriable(monkeypatch) -> None:
    """工具返回非 retriable 错误 → 不重试，直接 FAILED。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    # get_metadata for "get_weather" returns non-retriable by default
    tool_name = "get_weather"
    resp1 = _make_tool_call_response(tool_name=tool_name, tool_args='{"city": "beijing"}')
    resp2 = _make_fake_llm_response(content="Fallback after tool error")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])
    await _mock_llm_and_tools(
        monkeypatch,
        mock_client,
        handlers={
            tool_name: MagicMock(
                return_value={"status": "failed", "error": {"message": "API quota exceeded"}}
            ),
        },
    )
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "weather?"}],
        user_id="user-1",
    )

    started = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_STARTED
    ]
    completed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_COMPLETED
    ]
    failed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_FAILED
    ]

    assert len(started) == 1
    assert len(completed) == 0
    assert len(failed) == 1
    f = failed[0]
    assert f.success is False
    assert f.retry_count == 0
    assert "API quota exceeded" in f.error

    assert "reply" in result


async def test_tool_invocation_retry_then_success(monkeypatch) -> None:
    """工具重试后成功 → retry_count > 0，最终 COMPLETED。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    # get_metadata for "web_search" has retryable=True, max_retries=2
    tool_name = "search_candidates"
    _register_retryable_tool(monkeypatch, tool_name, max_retries=2)
    fail_resp = {"status": "failed", "error": {"message": "rate limited"}}
    ok_resp = {"candidates": ["found it"]}

    mock_handler = MagicMock()
    mock_handler.side_effect = [fail_resp, fail_resp, ok_resp]

    resp1 = _make_tool_call_response(tool_name=tool_name, tool_args='{"query": "test"}')
    resp2 = _make_fake_llm_response(content="Search done")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])
    await _mock_llm_and_tools(
        monkeypatch,
        mock_client,
        handlers={tool_name: mock_handler},
    )
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "search"}],
        user_id="user-1",
    )

    started = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_STARTED
    ]
    completed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_COMPLETED
    ]
    failed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_FAILED
    ]

    assert len(started) == 1
    assert len(completed) == 1
    assert len(failed) == 0
    c = completed[0]
    assert c.success is True
    assert c.retry_count == 2  # 两次失败后第三次成功
    assert c.duration_ms is not None and c.duration_ms >= 0

    assert result["reply"] == "Search done"


async def test_tool_invocation_all_retries_exhausted(monkeypatch) -> None:
    """工具所有重试耗尽 → 只有 STARTED + FAILED。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    tool_name = "search_candidates"
    _register_retryable_tool(monkeypatch, tool_name, max_retries=2)
    fail_resp = {"status": "failed", "error": {"message": "server down"}}

    mock_handler = MagicMock(return_value=fail_resp)

    resp1 = _make_tool_call_response(tool_name=tool_name, tool_args='{"query": "test"}')
    resp2 = _make_fake_llm_response(content="Fallback")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])
    await _mock_llm_and_tools(
        monkeypatch,
        mock_client,
        handlers={tool_name: mock_handler},
    )
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "search"}],
        user_id="user-1",
    )

    started = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_STARTED
    ]
    completed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_COMPLETED
    ]
    failed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_FAILED
    ]

    assert len(started) == 1
    assert len(completed) == 0
    assert len(failed) == 1
    f = failed[0]
    assert f.success is False
    assert f.retry_count == 2  # web_search max_retries=2, 3 attempts total
    assert "server down" in f.error

    assert "reply" in result


async def test_tool_invocation_unknown_tool(monkeypatch) -> None:
    """未知工具 → STARTED + FAILED。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    resp1 = _make_tool_call_response(tool_name="nonexistent_tool", tool_args="{}")
    resp2 = _make_fake_llm_response(content="No such tool")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])
    await _mock_llm_and_tools(
        monkeypatch,
        mock_client,
        handlers={},  # no handlers => nonexistent_tool won't be found
    )
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "do something"}],
        user_id="user-1",
    )

    started = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_STARTED
    ]
    failed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_FAILED
    ]

    assert len(started) == 1
    assert len(failed) == 1
    f = failed[0]
    assert f.success is False
    assert "Unknown tool" in f.error
    assert f.tool_name == "nonexistent_tool"

    assert "reply" in result


async def test_tool_invocation_exception(monkeypatch) -> None:
    """工具 handler 抛异常 → STARTED + FAILED，不重试（exception 只对 retryable 重试）。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    tool_name = "get_current_time"
    mock_handler = MagicMock(side_effect=ValueError("invalid argument"))

    resp1 = _make_tool_call_response(tool_name=tool_name, tool_args="{}")
    resp2 = _make_fake_llm_response(content="Tool crashed")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])
    await _mock_llm_and_tools(
        monkeypatch,
        mock_client,
        handlers={tool_name: mock_handler},
    )
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "time?"}],
        user_id="user-1",
    )

    started = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_STARTED
    ]
    failed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_FAILED
    ]

    assert len(started) == 1
    assert len(failed) == 1
    f = failed[0]
    assert f.success is False
    assert "invalid argument" in f.error

    assert "reply" in result


async def test_tool_invocation_retriable_exception(monkeypatch) -> None:
    """工具 handler 抛异常且工具可重试 → 重试后成功。"""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())
    await _mock_orchestrator_fallback(monkeypatch)

    tool_name = "search_candidates"
    _register_retryable_tool(monkeypatch, tool_name, max_retries=1)
    mock_handler = MagicMock()
    # First call raises, second succeeds
    mock_handler.side_effect = [
        ConnectionError("network glitch"),
        {"candidates": ["found it"]},
    ]

    resp1 = _make_tool_call_response(tool_name=tool_name, tool_args='{"query": "test"}')
    resp2 = _make_fake_llm_response(content="Search finally worked")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])
    await _mock_llm_and_tools(
        monkeypatch,
        mock_client,
        handlers={tool_name: mock_handler},
    )
    await _mock_contextbuilder_fallback(monkeypatch)

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "search"}],
        user_id="user-1",
    )

    started = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_STARTED
    ]
    completed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_COMPLETED
    ]
    failed = [
        e for e in spy.tool_call_events
        if e.event_type == EventType.TOOL_INVOCATION_FAILED
    ]

    assert len(started) == 1
    assert len(completed) == 1
    assert len(failed) == 0
    c = completed[0]
    assert c.success is True
    assert c.retry_count == 1

    assert result["reply"] == "Search finally worked"
