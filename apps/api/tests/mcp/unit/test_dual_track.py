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
