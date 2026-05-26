"""Agent Memory API tests: CRUD operations via in-memory fallback."""

import pytest
from unittest.mock import AsyncMock, patch

MEMORY_BASE = "/api/v1/memory"


@pytest.mark.asyncio
async def test_memory_write_and_read(client):
    """写入记忆后应能正确读取。"""
    with patch("app.api.memory.get_redis", side_effect=ConnectionError("No Redis")):
        write_resp = await client.post(f"{MEMORY_BASE}/write", json={
            "session_id": "session-a",
            "key": "candidate_123",
            "value": {"name": "张三", "score": 85},
        })
    assert write_resp.status_code == 200
    wdata = write_resp.json()
    assert wdata["success"] is True
    assert wdata["key"] == "candidate_123"
    assert wdata["value"]["name"] == "张三"
    assert wdata["value"]["score"] == 85
    assert wdata["created_at"] != ""

    with patch("app.api.memory.get_redis", side_effect=ConnectionError("No Redis")):
        read_resp = await client.post(f"{MEMORY_BASE}/read", json={
            "session_id": "session-a",
            "key": "candidate_123",
        })
    assert read_resp.status_code == 200
    rdata = read_resp.json()
    assert rdata["success"] is True
    assert rdata["key"] == "candidate_123"
    assert rdata["value"]["name"] == "张三"


@pytest.mark.asyncio
async def test_memory_read_missing_returns_empty(client):
    """读取不存在的键应返回空 value。"""
    with patch("app.api.memory.get_redis", side_effect=ConnectionError("No Redis")):
        resp = await client.post(f"{MEMORY_BASE}/read", json={
            "session_id": "session-b",
            "key": "nonexistent",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["value"] == {}


@pytest.mark.asyncio
async def test_memory_delete(client):
    """删除后读取应返回空。"""
    with patch("app.api.memory.get_redis", side_effect=ConnectionError("No Redis")):
        await client.post(f"{MEMORY_BASE}/write", json={
            "session_id": "session-c",
            "key": "temp_key",
            "value": {"data": "will be deleted"},
        })

        del_resp = await client.post(f"{MEMORY_BASE}/delete", json={
            "session_id": "session-c",
            "key": "temp_key",
        })
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    with patch("app.api.memory.get_redis", side_effect=ConnectionError("No Redis")):
        read_resp = await client.post(f"{MEMORY_BASE}/read", json={
            "session_id": "session-c",
            "key": "temp_key",
        })
    assert read_resp.json()["value"] == {}


@pytest.mark.asyncio
async def test_memory_keys(client):
    """列出 session 下的所有键。"""
    with patch("app.api.memory.get_redis", side_effect=ConnectionError("No Redis")):
        for i in range(3):
            await client.post(f"{MEMORY_BASE}/write", json={
                "session_id": "session-d",
                "key": f"k_{i}",
                "value": {"idx": i},
            })

        resp = await client.post(f"{MEMORY_BASE}/keys", json={
            "session_id": "session-d",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["keys"]) == 3
    assert "k_0" in data["keys"]
    assert "k_1" in data["keys"]
    assert "k_2" in data["keys"]


@pytest.mark.asyncio
async def test_memory_keys_empty_session(client):
    """没有记忆的 session 应返回空列表。"""
    with patch("app.api.memory.get_redis", side_effect=ConnectionError("No Redis")):
        resp = await client.post(f"{MEMORY_BASE}/keys", json={
            "session_id": "empty-session",
        })
    assert resp.status_code == 200
    assert resp.json()["keys"] == []


@pytest.mark.asyncio
async def test_memory_write_validation(client):
    """空 session_id 或 key 应被拒绝。"""
    resp = await client.post(f"{MEMORY_BASE}/write", json={
        "session_id": "",
        "key": "test",
        "value": {},
    })
    assert resp.status_code == 422

    resp = await client.post(f"{MEMORY_BASE}/write", json={
        "session_id": "s",
        "key": "",
        "value": {},
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_memory_write_via_redis(client):
    """写入记忆时优先走 Redis 路径（不 mock get_redis）。"""
    resp = await client.post(f"{MEMORY_BASE}/write", json={
        "session_id": "redis-session",
        "key": "redis-key-1",
        "value": {"source": "redis"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["key"] == "redis-key-1"
    assert data["value"]["source"] == "redis"
    assert data["expires_at"] is not None

    read_resp = await client.post(f"{MEMORY_BASE}/read", json={
        "session_id": "redis-session",
        "key": "redis-key-1",
    })
    assert read_resp.json()["value"]["source"] == "redis"


@pytest.mark.asyncio
async def test_memory_delete_nonexistent(client):
    """删除不存在的键返回 success=False。"""
    with patch("app.api.memory.get_redis", side_effect=ConnectionError("No Redis")):
        resp = await client.post(f"{MEMORY_BASE}/delete", json={
            "session_id": "no-session",
            "key": "nonexistent-key",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["key"] == "nonexistent-key"
