"""v0.3 §3.5 dual-track pytest — supervisor 失败 → fallback in-process。

验 §3.3 逻辑：
  1. _subprocess_call 抛 SubprocessDown → call_tool 兜底到 _inprocess_call
  2. _subprocess_call 正常返回 → call_tool 不调 _inprocess_call
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.host import MCPHost, SubprocessDown


@pytest.mark.asyncio
async def test_supervisor_down_fallback_to_inprocess():
    """subprocess 抛 SubprocessDown → 调 calc → 期望 in-process 返 6。"""
    host = MCPHost()

    with patch.object(
        host, "_subprocess_call", side_effect=SubprocessDown("test")
    ) as mock_sp:
        with patch.object(
            host, "_inprocess_call", new_callable=AsyncMock, return_value="6"
        ) as mock_fb:
            result = await host.call_tool("calculate", {"expression": "2*3"})

    assert result == "6"
    mock_sp.assert_called_once_with("calculate", {"expression": "2*3"}, user_id=None)
    mock_fb.assert_called_once_with("calculate", {"expression": "2*3"})


@pytest.mark.asyncio
async def test_supervisor_up_uses_subprocess_path():
    """subprocess 正常 → 走 subprocess 路径，不调 in-process。"""
    host = MCPHost()

    with patch.object(
        host, "_subprocess_call", new_callable=AsyncMock, return_value="6"
    ) as mock_sp:
        with patch.object(
            host, "_inprocess_call", new_callable=AsyncMock
        ) as mock_fb:
            result = await host.call_tool("calculate", {"expression": "2*3"})

    assert result == "6"
    mock_sp.assert_called_once_with("calculate", {"expression": "2*3"}, user_id=None)
    mock_fb.assert_not_called()


@pytest.mark.asyncio
async def test_call_timeout_fallback_to_inprocess():
    """CallTimeout 异常同样触发 fallback（v0.3 §3.2 F-3 网络卡死场景）。"""
    from app.mcp.host import CallTimeout

    host = MCPHost()

    with patch.object(
        host, "_subprocess_call", side_effect=CallTimeout("5s timeout")
    ) as mock_sp:
        with patch.object(
            host, "_inprocess_call", new_callable=AsyncMock, return_value="timeout_fallback"
        ) as mock_fb:
            result = await host.call_tool("calculate", {"expression": "2*3"})

    assert result == "timeout_fallback"
    mock_sp.assert_called_once()
    mock_fb.assert_called_once()


@pytest.mark.asyncio
async def test_other_exceptions_not_caught_by_dual_track():
    """非 SubprocessDown/CallTimeout 异常不被 dual-track 接住，向上抛。"""
    host = MCPHost()

    with patch.object(
        host, "_subprocess_call", side_effect=ValueError("unexpected")
    ):
        with patch.object(
            host, "_inprocess_call", new_callable=AsyncMock
        ) as mock_fb:
            with pytest.raises(ValueError, match="unexpected"):
                await host.call_tool("calculate", {"expression": "2*3"})

    mock_fb.assert_not_called()


@pytest.mark.asyncio
async def test_inprocess_call_dispatches_to_real_handler():
    """v0.4a: _inprocess_call 真正调 agent_service._get_handlers()。

    之前 PR-8 是 stub，PR-9 验证结构，现在接 agent_service 兜底。
    mock _get_handlers 返回一个 async handler，验证 _inprocess_call
    调它并 wrap result。
    """
    from app.mcp.host import MCPHost

    host = MCPHost()

    async def fake_handler(**kwargs):
        return {"computed": 2 * int(kwargs["n"])}

    with patch("app.services.agent_service._get_handlers") as mock_get:
        mock_get.return_value = {"compute": fake_handler}

        result = await host._inprocess_call("compute", {"n": 21})

    assert result == {"status": "success", "data": {"computed": 42}}
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_inprocess_call_handles_sync_handler():
    """v0.4a: handler 是 sync 函数时也支持（用 asyncio.iscoroutine 区分）。"""
    from app.mcp.host import MCPHost

    host = MCPHost()

    def sync_handler(**kwargs):
        return {"synced": True, "input": kwargs}

    with patch("app.services.agent_service._get_handlers") as mock_get:
        mock_get.return_value = {"sync_op": sync_handler}

        result = await host._inprocess_call("sync_op", {"x": 1})

    assert result == {"status": "success", "data": {"synced": True, "input": {"x": 1}}}


@pytest.mark.asyncio
async def test_inprocess_call_returns_error_when_no_handler():
    """v0.4a: tool 不在 _get_handlers 字典时返 NO_INPROCESS_HANDLER。"""
    from app.mcp.host import MCPHost

    host = MCPHost()

    with patch("app.services.agent_service._get_handlers") as mock_get:
        mock_get.return_value = {}  # 没有任何 handler

        result = await host._inprocess_call("nonexistent", {})

    assert result["status"] == "failed"
    assert result["error"]["code"] == "NO_INPROCESS_HANDLER"


@pytest.mark.asyncio
async def test_inprocess_call_wraps_already_formatted_result():
    """v0.4a: handler 已返 {"status": ..., "data": ...} 时直接透传，不重复 wrap。"""
    from app.mcp.host import MCPHost

    host = MCPHost()

    async def formatted_handler(**kwargs):
        return {"status": "success", "data": "already-formatted"}

    with patch("app.services.agent_service._get_handlers") as mock_get:
        mock_get.return_value = {"fmt_op": formatted_handler}

        result = await host._inprocess_call("fmt_op", {})

    assert result == {"status": "success", "data": "already-formatted"}


@pytest.mark.asyncio
async def test_inprocess_call_catches_handler_exceptions():
    """v0.4a: handler 抛异常时返 INPROCESS_ERROR，不向上传。"""
    from app.mcp.host import MCPHost

    host = MCPHost()

    async def broken_handler(**kwargs):
        raise RuntimeError("handler crashed")

    with patch("app.services.agent_service._get_handlers") as mock_get:
        mock_get.return_value = {"broken": broken_handler}

        result = await host._inprocess_call("broken", {})

    assert result["status"] == "failed"
    assert result["error"]["code"] == "INPROCESS_ERROR"
    assert "handler crashed" in result["error"]["message"]
