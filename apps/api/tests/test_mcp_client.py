"""Tests for MCP JSON-RPC 2.0 protocol client."""

import json
import pytest
from unittest.mock import AsyncMock, patch

import httpx

from app.mcp.client import (
    _build_auth_header,
    _rpc_call,
    mcp_initialize,
    mcp_list_tools,
    mcp_call_tool,
)


def _mock_httpx_client(json_data, status_code=200):
    """Create a mock httpx.AsyncClient context manager."""
    from unittest.mock import Mock
    mock_resp = Mock()
    mock_resp.json = Mock(return_value=json_data)
    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code}", request=Mock(),
            response=Mock(status_code=status_code),
        )
    else:
        mock_resp.raise_for_status = Mock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


MOCK_SUCCESS = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {"serverInfo": {"name": "test-server", "version": "1.0"}},
}


class TestBuildAuthHeader:
    def test_no_token(self):
        assert _build_auth_header("none", "") == ""

    def test_bearer(self):
        assert _build_auth_header("bearer", "tok123") == "Bearer tok123"

    def test_basic(self):
        result = _build_auth_header("basic", "user:pass")
        assert result.startswith("Basic ")

    def test_basic_encoding(self):
        import base64
        result = _build_auth_header("basic", "admin:secret")
        expected = f"Basic {base64.b64encode(b'admin:secret').decode()}"
        assert result == expected

    def test_unknown_auth_type(self):
        assert _build_auth_header("digest", "tok") == ""


@pytest.mark.asyncio
async def test_rpc_call_success():
    mock_client = _mock_httpx_client(MOCK_SUCCESS)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _rpc_call("http://example.com/mcp", {})
    assert result == {"serverInfo": {"name": "test-server", "version": "1.0"}}


@pytest.mark.asyncio
async def test_rpc_call_rpc_error():
    err_resp = {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}}
    mock_client = _mock_httpx_client(err_resp)
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="MCP error"):
            await _rpc_call("http://example.com/mcp", {})


@pytest.mark.asyncio
async def test_rpc_call_http_error():
    mock_client = _mock_httpx_client({"error": "unauthorized"}, status_code=401)
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await _rpc_call("http://example.com/mcp", {})


@pytest.mark.asyncio
async def test_rpc_call_connection_error():
    """ConnectError from the client's __aenter__ (connection refused)."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.ConnectError):
            await _rpc_call("http://example.com/mcp", {})


@pytest.mark.asyncio
async def test_mcp_initialize_success():
    mock_client = _mock_httpx_client(MOCK_SUCCESS)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await mcp_initialize("http://example.com/mcp", "Bearer tok")
    assert result["serverInfo"]["name"] == "test-server"


@pytest.mark.asyncio
async def test_mcp_initialize_with_notification():
    """Should send initialize, then notifications/initialized."""
    from unittest.mock import Mock
    calls = []

    async def post_side(url, **kwargs):
        calls.append(kwargs.get("json", {}))
        resp = Mock()
        resp.json = Mock(return_value=MOCK_SUCCESS)
        resp.raise_for_status = Mock()
        return resp

    mock_cli = AsyncMock()
    mock_cli.post = AsyncMock(side_effect=post_side)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cli)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_cm):
        result = await mcp_initialize("http://example.com/mcp")
    assert len(calls) == 2
    assert calls[0]["method"] == "initialize"
    assert calls[1]["method"] == "notifications/initialized"
    assert result["serverInfo"]["name"] == "test-server"


@pytest.mark.asyncio
async def test_mcp_initialize_notification_failure_ignored():
    """If the notifications/initialized call fails, it's silently ignored."""
    from unittest.mock import Mock
    call_no = 0

    async def post_side(url, **kwargs):
        nonlocal call_no
        call_no += 1
        if call_no == 1:
            resp = Mock()
            resp.json = Mock(return_value=MOCK_SUCCESS)
            resp.raise_for_status = Mock()
            return resp
        raise httpx.RequestError("notify failed")

    mock_cli = AsyncMock()
    mock_cli.post = AsyncMock(side_effect=post_side)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cli)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_cm):
        result = await mcp_initialize("http://example.com/mcp")
    assert result["serverInfo"]["name"] == "test-server"


@pytest.mark.asyncio
async def test_mcp_list_tools():
    json_data = {
        "jsonrpc": "2.0",
        "result": {
            "tools": [
                {"name": "tool1", "description": "First tool"},
                {"name": "tool2", "description": "Second tool"},
            ]
        },
    }
    mock_client = _mock_httpx_client(json_data)
    with patch("httpx.AsyncClient", return_value=mock_client):
        tools = await mcp_list_tools("http://example.com/mcp")
    assert len(tools) == 2
    assert tools[0]["name"] == "tool1"


@pytest.mark.asyncio
async def test_mcp_list_tools_empty():
    mock_client = _mock_httpx_client({"jsonrpc": "2.0", "result": {}})
    with patch("httpx.AsyncClient", return_value=mock_client):
        assert await mcp_list_tools("http://example.com/mcp") == []


@pytest.mark.asyncio
async def test_mcp_call_tool():
    json_data = {
        "jsonrpc": "2.0",
        "result": {"content": [{"type": "text", "text": "Result data"}]},
    }
    mock_client = _mock_httpx_client(json_data)
    with patch("httpx.AsyncClient", return_value=mock_client):
        content = await mcp_call_tool("http://example.com/mcp", "get_weather", {"city": "Beijing"})
    assert content == [{"type": "text", "text": "Result data"}]


@pytest.mark.asyncio
async def test_mcp_call_tool_no_content():
    mock_client = _mock_httpx_client({"jsonrpc": "2.0", "result": {}})
    with patch("httpx.AsyncClient", return_value=mock_client):
        assert await mcp_call_tool("http://example.com/mcp", "x", {}) == []


class TestTestConnection:
    """test_connection imported per-test to avoid pytest collecting it."""

    @pytest.mark.asyncio
    async def test_success(self):
        from app.mcp.client import test_connection

        init_resp = {"jsonrpc": "2.0", "result": {"serverInfo": {"name": "test-server"}}}
        tools_resp = {"jsonrpc": "2.0", "result": {"tools": [{"name": "greet"}]}}

        call_no = 0

        async def post_side(url, **kwargs):
            nonlocal call_no
            call_no += 1
            from unittest.mock import Mock
            if call_no == 1:
                resp = Mock()
                resp.json = Mock(return_value=init_resp)
            elif call_no == 2:
                resp = Mock()
                resp.json = Mock(return_value=init_resp)  # notification
            else:
                resp = Mock()
                resp.json = Mock(return_value=tools_resp)
            resp.raise_for_status = Mock()
            return resp

        mock_cli = AsyncMock()
        mock_cli.post = AsyncMock(side_effect=post_side)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_cli)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_cm):
            result = await test_connection("http://example.com/mcp", "bearer", "tok")
        assert result["success"] is True
        assert result["server_name"] == "test-server"
        assert len(result["tools"]) == 1

    @pytest.mark.asyncio
    async def test_http_status_error(self):
        from app.mcp.client import test_connection
        with patch("app.mcp.client.mcp_initialize", side_effect=httpx.HTTPStatusError(
            "403", request=AsyncMock(), response=AsyncMock(status_code=403, text="Forbidden")
        )):
            result = await test_connection("http://example.com/mcp")
        assert result["success"] is False
        assert "403" in result["error"]

    @pytest.mark.asyncio
    async def test_request_error(self):
        from app.mcp.client import test_connection
        with patch("app.mcp.client.mcp_initialize", side_effect=httpx.RequestError("timeout")):
            result = await test_connection("http://example.com/mcp")
        assert result["success"] is False
        assert "连接失败" in result["error"]

    @pytest.mark.asyncio
    async def test_json_decode_error(self):
        from app.mcp.client import test_connection
        with patch("app.mcp.client.mcp_initialize", side_effect=json.JSONDecodeError("bad json", "", 0)):
            result = await test_connection("http://example.com/mcp")
        assert result["success"] is False
        assert "协议错误" in result["error"]

    @pytest.mark.asyncio
    async def test_runtime_error(self):
        from app.mcp.client import test_connection
        with patch("app.mcp.client.mcp_initialize", side_effect=RuntimeError("MCP error [-32601]: Method not found")):
            result = await test_connection("http://example.com/mcp")
        assert result["success"] is False
        assert "协议错误" in result["error"]

    @pytest.mark.asyncio
    async def test_unexpected_error(self):
        from app.mcp.client import test_connection
        with patch("app.mcp.client.mcp_initialize", side_effect=ValueError("weird")):
            result = await test_connection("http://example.com/mcp")
        assert result["success"] is False
        assert "未知错误" in result["error"]
