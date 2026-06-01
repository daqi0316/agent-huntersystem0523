"""Tests for MCP Server connection manager."""

import pytest
from unittest.mock import AsyncMock, patch

from app.mcp.manager import MCPManager, MCPServerState


@pytest.mark.asyncio
async def test_register_new_server():
    mgr = MCPManager()
    await mgr.register("srv-1", "test-server", "http://example.com/mcp")
    assert "srv-1" in mgr._servers
    state = mgr._servers["srv-1"]
    assert state.name == "test-server"
    assert state.url == "http://example.com/mcp"


@pytest.mark.asyncio
async def test_register_with_auth():
    mgr = MCPManager()
    await mgr.register("srv-1", "secure", "http://example.com/mcp", auth_type="bearer", auth_token="tok123")
    state = mgr._servers["srv-1"]
    assert state.auth_header == "Bearer tok123"


@pytest.mark.asyncio
async def test_register_with_tools_cache():
    mgr = MCPManager()
    tools = [{"name": "tool1"}]
    await mgr.register("srv-1", "cached", "http://example.com/mcp", tools_cache_data=tools)
    assert mgr._servers["srv-1"].tools_cache == tools


@pytest.mark.asyncio
async def test_register_updates_existing():
    mgr = MCPManager()
    await mgr.register("srv-1", "old", "http://old.url")
    await mgr.register("srv-1", "new", "http://new.url", tools_cache_data=[{"name": "t1"}])
    state = mgr._servers["srv-1"]
    assert state.name == "new"
    assert state.url == "http://new.url"
    assert state.tools_cache == [{"name": "t1"}]


@pytest.mark.asyncio
async def test_register_keeps_old_cache_when_not_provided():
    mgr = MCPManager()
    await mgr.register("srv-1", "test", "http://url", tools_cache_data=[{"name": "old_tool"}])
    await mgr.register("srv-1", "updated", "http://new-url")  # no tools_cache_data
    assert mgr._servers["srv-1"].tools_cache == [{"name": "old_tool"}]


@pytest.mark.asyncio
async def test_unregister():
    mgr = MCPManager()
    await mgr.register("srv-1", "test", "http://url")
    await mgr.unregister("srv-1")
    assert "srv-1" not in mgr._servers


@pytest.mark.asyncio
async def test_unregister_unknown():
    mgr = MCPManager()
    await mgr.unregister("nonexistent")  # should not raise


@pytest.mark.asyncio
async def test_discover_tools_success():
    mgr = MCPManager()
    await mgr.register("srv-1", "test", "http://url")
    tools = [{"name": "tool_a"}, {"name": "tool_b"}]
    with patch("app.mcp.manager.mcp_list_tools", new=AsyncMock(return_value=tools)):
        result = await mgr.discover_tools("srv-1")
    assert result == tools
    assert mgr._servers["srv-1"].tools_cache == tools
    assert mgr._servers["srv-1"].last_heartbeat is not None


@pytest.mark.asyncio
async def test_discover_tools_unknown_server():
    mgr = MCPManager()
    assert await mgr.discover_tools("no-such-server") == []


@pytest.mark.asyncio
async def test_discover_tools_failure_returns_cache():
    mgr = MCPManager()
    await mgr.register("srv-1", "test", "http://url", tools_cache_data=[{"name": "cached"}])
    with patch("app.mcp.manager.mcp_list_tools", side_effect=Exception("network error")):
        result = await mgr.discover_tools("srv-1")
    assert result == [{"name": "cached"}]  # returns cache on failure


@pytest.mark.asyncio
async def test_call_tool_success():
    mgr = MCPManager()
    await mgr.register("srv-1", "test", "http://url")
    with patch("app.mcp.manager.mcp_call_tool", new=AsyncMock(return_value=[{"type": "text", "text": "42"}])):
        result = await mgr.call_tool("srv-1", "calculator", {"a": 1})
    assert result == "42"


@pytest.mark.asyncio
async def test_call_tool_unknown_server():
    mgr = MCPManager()
    result = await mgr.call_tool("no-such", "tool", {})
    assert "未注册" in result


@pytest.mark.asyncio
async def test_call_tool_failure_returns_error_text():
    mgr = MCPManager()
    await mgr.register("srv-1", "test", "http://url")
    with patch("app.mcp.manager.mcp_call_tool", side_effect=RuntimeError("I/O error")):
        result = await mgr.call_tool("srv-1", "tool", {})
    assert "工具调用失败" in result


@pytest.mark.asyncio
async def test_get_all_tools_empty():
    mgr = MCPManager()
    assert mgr.get_all_tools() == []


@pytest.mark.asyncio
async def test_get_all_tools():
    mgr = MCPManager()
    await mgr.register("srv-1", "s1", "http://u1", tools_cache_data=[
        {"name": "t1", "inputSchema": {"type": "object"}},
    ])
    await mgr.register("srv-2", "s2", "http://u2", tools_cache_data=[
        {"name": "t2", "inputSchema": {"type": "object"}},
    ])
    tools = mgr.get_all_tools()
    assert len(tools) == 2
    names = [t["function"]["name"] for t in tools]
    assert "t1" in names
    assert "t2" in names


@pytest.mark.asyncio
async def test_get_all_tools_skips_conversion_errors():
    mgr = MCPManager()
    await mgr.register("srv-1", "s1", "http://u1", tools_cache_data=[
        {"name": "good", "inputSchema": {"type": "object"}},
        None,  # skipped by if tool is None guard
    ])
    tools = mgr.get_all_tools()
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "good"


@pytest.mark.asyncio
async def test_get_handler_found():
    mgr = MCPManager()
    await mgr.register("srv-1", "s1", "http://url", tools_cache_data=[
        {"name": "greet", "description": "Say hello"},
    ])
    handler = mgr.get_handler("greet")
    assert handler is not None
    with patch("app.mcp.manager.mcp_call_tool", new=AsyncMock(return_value=[{"type": "text", "text": "hi"}])):
        result = await handler(name="World")
    assert result == "hi"


@pytest.mark.asyncio
async def test_get_handler_not_found():
    mgr = MCPManager()
    await mgr.register("srv-1", "s1", "http://url", tools_cache_data=[])
    assert mgr.get_handler("nonexistent") is None


@pytest.mark.asyncio
async def test_get_tool_owner():
    mgr = MCPManager()
    await mgr.register("srv-1", "s1", "http://url", tools_cache_data=[{"name": "t1"}])
    owner = mgr.get_tool_owner("t1")
    assert owner is not None
    assert owner.server_id == "srv-1"


@pytest.mark.asyncio
async def test_get_tool_owner_not_found():
    mgr = MCPManager()
    assert mgr.get_tool_owner("nonexistent") is None


@pytest.mark.asyncio
async def test_refresh_all():
    mgr = MCPManager()
    await mgr.register("srv-1", "s1", "http://u1")
    await mgr.register("srv-2", "s2", "http://u2")

    with patch("app.mcp.manager.mcp_list_tools", new=AsyncMock(return_value=[{"name": "tool"}])):
        count = await mgr.refresh_all()
    assert count == 2


@pytest.mark.asyncio
async def test_refresh_all_partial_failure():
    mgr = MCPManager()
    await mgr.register("srv-ok", "ok", "http://ok")
    await mgr.register("srv-fail", "fail", "http://fail")

    original_discover = mgr.discover_tools

    async def mock_discover(sid):
        if sid == "srv-fail":
            raise Exception("down")
        return await original_discover(sid)

    mgr.discover_tools = mock_discover
    with patch("app.mcp.manager.mcp_list_tools", new=AsyncMock(return_value=[{"name": "tool"}])):
        count = await mgr.refresh_all()
    assert count == 1
    assert mgr._servers["srv-fail"].tools_cache == []
    assert mgr._servers["srv-ok"].tools_cache == [{"name": "tool"}]


@pytest.mark.asyncio
async def test_get_server_info():
    mgr = MCPManager()
    await mgr.register("srv-1", "test", "http://url")
    info = mgr.get_server_info("srv-1")
    assert info is not None
    assert info["server_id"] == "srv-1"


@pytest.mark.asyncio
async def test_get_server_info_not_found():
    mgr = MCPManager()
    assert mgr.get_server_info("no-such") is None


@pytest.mark.asyncio
async def test_list_servers():
    mgr = MCPManager()
    await mgr.register("srv-1", "s1", "http://u1")
    await mgr.register("srv-2", "s2", "http://u2")
    servers = mgr.list_servers()
    assert len(servers) == 2
    ids = [s["server_id"] for s in servers]
    assert "srv-1" in ids
    assert "srv-2" in ids


class TestMCPServerState:
    def test_to_dict_without_heartbeat(self):
        state = MCPServerState("srv-1", "test", "http://url", "Bearer tok")
        d = state.to_dict()
        assert d["server_id"] == "srv-1"
        assert d["name"] == "test"
        assert d["tools_count"] == 0
        assert d["last_heartbeat"] is None

    def test_to_dict_with_heartbeat(self):
        from datetime import datetime, timezone
        state = MCPServerState("srv-1", "test", "http://url", "")
        state.last_heartbeat = datetime(2024, 1, 1, tzinfo=timezone.utc)
        d = state.to_dict()
        assert d["last_heartbeat"] is not None


class TestMCPManagerSingleton:
    def test_global_instance_exists(self):
        from app.mcp.manager import mcp_manager
        assert mcp_manager is not None
        assert isinstance(mcp_manager, MCPManager)
