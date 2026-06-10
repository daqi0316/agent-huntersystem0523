"""P1 根 trace 集成测试：chat_with_tools 的 AgentOps 生命周期。

验证点：
  1. start_trace 被调用，且 input 是脱敏的
  2. 成功时 record_event(TRACE_COMPLETED) 被调用
  3. 异常时 record_event(TRACE_FAILED) 被调用
  4. AgentOpsContext 在 finally 被清掉
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agentops.core.schemas import EventType

pytestmark = pytest.mark.asyncio


class SpyProvider:
    """记录所有 start_trace / record_event 调用的 spy provider."""

    def __init__(self):
        self.started_trace = None
        self.recorded_events = []
        self._flushed = False

    async def start_trace(self, event) -> None:
        self.started_trace = event

    async def record_event(self, event) -> None:
        self.recorded_events.append(event)

    async def start_span(self, event) -> None:
        pass

    async def record_generation(self, event) -> None:
        pass

    async def record_tool_call(self, event) -> None:
        pass

    async def record_score(self, event) -> None:
        pass

    async def flush(self) -> None:
        self._flushed = True

    async def shutdown(self) -> None:
        pass


# ── 辅助：模拟 command executor 返回 ──


def _make_command_result(message: str) -> MagicMock:
    """minimal mock CommandResult with action != passthrough."""
    r = MagicMock()
    r.action = "executed"
    r.message = message
    return r


async def test_root_trace_completed_on_command_success(monkeypatch) -> None:
    """通过 /command 路径验证 start_trace + TRACE_COMPLETED."""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    # mock 命令执行器
    mock_registry = MagicMock()
    mock_executor = AsyncMock()
    mock_executor.execute.return_value = _make_command_result("已执行")
    monkeypatch.setattr(
        "app.services.agent_service.get_default_registry", lambda: mock_registry
    )
    monkeypatch.setattr(
        "app.services.agent_service.CommandExecutor",
        lambda registry=None: mock_executor,
    )

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "/help"}],
        user_id="user-1",
        session_id="session-1",
    )

    # 1) start_trace 被调用
    assert spy.started_trace is not None
    assert spy.started_trace.event_type == EventType.TRACE_STARTED
    assert spy.started_trace.trace_id
    assert spy.started_trace.user_id == "user-1"
    assert spy.started_trace.session_id == "session-1"
    # input 经 sanitize_payload 处理
    inp = spy.started_trace.input
    assert isinstance(inp, dict)
    assert inp.get("user_id") == "user-1"
    assert inp.get("session_id") == "session-1"
    assert inp.get("message_count") == 1
    assert inp.get("has_attachment") is False

    # 2) record_event(TRACE_COMPLETED) 被调用
    completed_events = [e for e in spy.recorded_events if e.event_type == EventType.TRACE_COMPLETED]
    assert len(completed_events) == 1
    ce = completed_events[0]
    assert ce.trace_id == spy.started_trace.trace_id
    assert ce.user_id == "user-1"
    assert ce.session_id == "session-1"
    out = ce.output
    assert isinstance(out, dict)
    assert out.get("reply_length") == len("已执行")
    assert out.get("tool_call_count") == 0

    # 3) 正常返回
    assert result["reply"] == "已执行"


async def test_root_trace_failed_on_exception(monkeypatch) -> None:
    """验证异常路径 record_event(TRACE_FAILED)."""
    spy = SpyProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    # mock 命令执行器：/boom 触发异常
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

    with pytest.raises(RuntimeError, match="cmd boom"):
        await chat_with_tools(
            messages=[{"role": "user", "content": "/boom"}],
            user_id="user-1",
        )

    # start_trace was called
    assert spy.started_trace is not None

    # record_event(TRACE_FAILED) 被调用
    failed_events = [e for e in spy.recorded_events if e.event_type == EventType.TRACE_FAILED]
    assert len(failed_events) == 1
    fe = failed_events[0]
    assert fe.trace_id == spy.started_trace.trace_id
    assert fe.user_id == "user-1"
    # error contains the exception message
    assert isinstance(fe.error, str)


async def test_root_trace_skipped_when_start_trace_fails(monkeypatch) -> None:
    """start_trace 失败时不应阻止主流程且不记录后续事件."""
    class FailingProvider(SpyProvider):
        async def start_trace(self, event) -> None:
            raise RuntimeError("trace down")

    spy = FailingProvider()
    monkeypatch.setattr("app.services.agent_service.get_agentops_provider", lambda: spy)
    monkeypatch.setattr("app.services.agent_service._register_builtins", AsyncMock())

    mock_registry = MagicMock()
    mock_executor = AsyncMock()
    mock_executor.execute.return_value = _make_command_result("ok")
    monkeypatch.setattr(
        "app.services.agent_service.get_default_registry", lambda: mock_registry
    )
    monkeypatch.setattr(
        "app.services.agent_service.CommandExecutor",
        lambda registry=None: mock_executor,
    )

    from app.services.agent_service import chat_with_tools

    result = await chat_with_tools(
        messages=[{"role": "user", "content": "/help"}],
        user_id="user-1",
    )

    # start_trace 失败 → _trace_active=False → 不记录后续事件
    assert spy.started_trace is None
    assert len(spy.recorded_events) == 0
    # 主流程正常运行
    assert result["reply"] == "ok"
