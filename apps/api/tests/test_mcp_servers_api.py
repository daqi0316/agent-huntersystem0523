"""API tests for app.api.mcp_servers — MCP Server CRUD + connection test."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


BASE = "/api/v1/mcp"


def _fake_server(**overrides) -> MagicMock:
    """Create a mock MCPServer ORM object."""
    server = MagicMock()
    server.id = overrides.get("id", str(uuid.uuid4()))
    server.name = overrides.get("name", "test-server")
    server.server_url = overrides.get("server_url", "http://localhost:9000")
    server.protocol = overrides.get("protocol", "sse")
    server.auth_type = overrides.get("auth_type", "none")
    server.auth_token = overrides.get("auth_token", None)
    server.enabled = overrides.get("enabled", True)
    server.tools_cache = overrides.get("tools_cache", None)
    server.last_heartbeat = overrides.get("last_heartbeat", None)
    server.created_at = overrides.get("created_at", "2026-01-01T00:00:00")
    server.updated_at = overrides.get("updated_at", "2026-01-01T00:00:00")
    return server


@pytest.fixture
def mock_db():
    """Override get_db dependency to return a mock AsyncSession."""
    from app.core.database import get_db
    session = AsyncMock()
    execute_result = MagicMock()
    # Support both .scalars().all() and .scalar_one_or_none()
    session.execute.return_value = execute_result

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_test_connection():
    """Patch test_connection to return a controlled response."""
    with patch("app.api.mcp_servers.test_connection") as mock:
        mock.return_value = AsyncMock()
        mock.return_value = {"success": True, "tools": [{"name": "tool1"}]}
        yield mock


@pytest.fixture
def mock_mcp_manager():
    """Patch mcp_manager.register and unregister."""
    with patch("app.api.mcp_servers.mcp_manager") as mock:
        mock.register = AsyncMock()
        mock.unregister = AsyncMock()
        yield mock


# ── _server_to_read helper ──


@patch("app.api.mcp_servers.json.loads")
def test_server_to_read_parses_tools_cache(mock_json_loads):
    mock_json_loads.return_value = [{"name": "cached_tool"}]
    server = _fake_server(tools_cache='[{"name": "real_tool"}]')
    from app.api.mcp_servers import _server_to_read
    result = _server_to_read(server)
    assert "tools_cache" in result


def test_server_to_read_none_tools_cache():
    server = _fake_server(tools_cache=None)
    from app.api.mcp_servers import _server_to_read
    result = _server_to_read(server)
    assert result["tools_cache"] is None


def test_server_to_read_invalid_tools_cache():
    server = _fake_server(tools_cache="not valid json{{{")
    from app.api.mcp_servers import _server_to_read
    result = _server_to_read(server)
    assert result["tools_cache"] is None


# ── GET /servers (list) ──


@pytest.mark.asyncio
async def test_list_servers(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [
        _fake_server(id="1", name="srv1"),
        _fake_server(id="2", name="srv2"),
    ]
    resp = await client.get(f"{BASE}/servers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]) == 2


# ── POST /servers (create) ──


@pytest.mark.asyncio
async def test_create_server(client, mock_db, mock_test_connection, mock_mcp_manager):
    mock_db.add = MagicMock()  # AsyncSession.add() is sync
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    resp = await client.post(
        f"{BASE}/servers",
        json={
            "name": "new-server",
            "server_url": "http://localhost:9000",
            "protocol": "sse",
            "auth_type": "none",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_mcp_manager.register.assert_called_once()


@patch("app.api.mcp_servers.test_connection")
@pytest.mark.asyncio
async def test_create_server_handles_connection_failure(mock_test_conn, client, mock_db, mock_mcp_manager):
    mock_test_conn.side_effect = Exception("Connection refused")
    mock_db.add = MagicMock()  # AsyncSession.add() is sync
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    resp = await client.post(
        f"{BASE}/servers",
        json={
            "name": "broken-server",
            "server_url": "http://invalid:9000",
            "protocol": "sse",
            "auth_type": "none",
        },
    )
    assert resp.status_code == 201
    # Should still create the server even if connection fails
    mock_db.add.assert_called_once()


# ── GET /servers/{id} ──


@pytest.mark.asyncio
async def test_get_server_found(client, mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = _fake_server(id="s1", name="found-srv")
    resp = await client.get(f"{BASE}/servers/s1")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_get_server_not_found(client, mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    resp = await client.get(f"{BASE}/servers/nonexistent")
    assert resp.status_code == 404


# ── PUT /servers/{id} ──


@pytest.mark.asyncio
async def test_update_server(client, mock_db, mock_test_connection, mock_mcp_manager):
    server = _fake_server(id="upd1", name="old-name")
    mock_db.execute.return_value.scalar_one_or_none.return_value = server
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    resp = await client.put(
        f"{BASE}/servers/upd1",
        json={"name": "new-name"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_mcp_manager.register.assert_called_once()


@pytest.mark.asyncio
async def test_update_server_not_found(client, mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    resp = await client.put(
        f"{BASE}/servers/nonexistent",
        json={"name": "ignored"},
    )
    assert resp.status_code == 404


@patch("app.api.mcp_servers.test_connection")
@pytest.mark.asyncio
async def test_update_server_rediscovers_tools_on_url_change(mock_test_conn, client, mock_db, mock_mcp_manager):
    mock_test_conn.return_value = {"success": True, "tools": [{"name": "new_tool"}]}
    server = _fake_server(id="upd2", name="srv", server_url="http://old:9000", tools_cache=json.dumps([{"name": "old_tool"}]))
    mock_db.execute.return_value.scalar_one_or_none.return_value = server
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    resp = await client.put(
        f"{BASE}/servers/upd2",
        json={"server_url": "http://new:9000"},
    )
    assert resp.status_code == 200
    mock_test_conn.assert_called_once()


# ── DELETE /servers/{id} ──


@pytest.mark.asyncio
async def test_delete_server(client, mock_db, mock_mcp_manager):
    server = _fake_server(id="del1")
    mock_db.execute.return_value.scalar_one_or_none.return_value = server
    mock_db.delete = AsyncMock()
    mock_db.commit = AsyncMock()

    resp = await client.delete(f"{BASE}/servers/del1")
    assert resp.status_code == 200
    mock_db.delete.assert_called_once_with(server)
    mock_mcp_manager.unregister.assert_called_once_with("del1")


@pytest.mark.asyncio
async def test_delete_server_not_found(client, mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    resp = await client.delete(f"{BASE}/servers/nonexistent")
    assert resp.status_code == 404


# ── POST /servers/test ──


@patch("app.api.mcp_servers.test_connection")
@pytest.mark.asyncio
async def test_test_connection(mock_test_conn, client):
    mock_test_conn.return_value = {"success": True, "tools": [{"name": "t1", "description": ""}], "error": ""}
    resp = await client.post(
        f"{BASE}/servers/test",
        json={"server_url": "http://test:9000", "auth_type": "none"},
    )
    assert resp.status_code == 200
    mock_test_conn.assert_called_once_with("http://test:9000", "none", "")


# ── POST /servers/{id}/test ──


@patch("app.api.mcp_servers.test_connection")
@pytest.mark.asyncio
async def test_test_existing_connection(mock_test_conn, client, mock_db):
    mock_test_conn.return_value = {"success": True, "tools": [], "error": ""}
    mock_db.execute.return_value.scalar_one_or_none.return_value = _fake_server(id="t1", server_url="http://srv:9000")

    resp = await client.post(f"{BASE}/servers/t1/test")
    assert resp.status_code == 200
    mock_test_conn.assert_called_once()


@patch("app.api.mcp_servers.test_connection")
@pytest.mark.asyncio
async def test_test_existing_connection_not_found(mock_test_conn, client, mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    resp = await client.post(f"{BASE}/servers/nonexistent/test")
    assert resp.status_code == 404
