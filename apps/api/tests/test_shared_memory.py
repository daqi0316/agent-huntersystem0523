"""Tests for SharedMemory — KV store with TTL and Redis fallback."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.shared_memory import (
    InMemoryBackend,
    SharedMemory,
    get_shared_memory,
)


# ── InMemoryBackend ──


@pytest.mark.asyncio
async def test_in_memory_set_get():
    mem = InMemoryBackend()
    await mem.set("k1", b"v1")
    assert await mem.get("k1") == b"v1"


@pytest.mark.asyncio
async def test_in_memory_get_missing():
    mem = InMemoryBackend()
    assert await mem.get("nope") is None


@pytest.mark.asyncio
async def test_in_memory_delete():
    mem = InMemoryBackend()
    await mem.set("k1", b"v1")
    assert await mem.delete("k1") is True
    assert await mem.get("k1") is None


@pytest.mark.asyncio
async def test_in_memory_exists():
    mem = InMemoryBackend()
    await mem.set("k1", b"v1")
    assert await mem.exists("k1") is True
    assert await mem.exists("nope") is False


@pytest.mark.asyncio
async def test_in_memory_keys():
    mem = InMemoryBackend()
    await mem.set("a:1", b"x")
    await mem.set("a:2", b"y")
    await mem.set("b:1", b"z")
    assert set(await mem.keys("a:*")) == {"a:1", "a:2"}
    assert len(await mem.keys("*")) == 3


@pytest.mark.asyncio
async def test_in_memory_ttl_expiry():
    mem = InMemoryBackend()
    await mem.set("k1", b"v1", ttl=0)  # already expired
    assert await mem.get("k1") is None
    assert await mem.exists("k1") is False


@pytest.mark.asyncio
async def test_in_memory_expire_and_ttl():
    mem = InMemoryBackend()
    await mem.set("k1", b"v1")
    assert await mem.ttl("k1") == -1  # no ttl
    assert await mem.expire("k1", 9999) is True
    ttl = await mem.ttl("k1")
    assert 1 <= ttl <= 9999
    assert await mem.expire("nope", 10) is False


@pytest.mark.asyncio
async def test_in_memory_clear():
    mem = InMemoryBackend()
    await mem.set("k1", b"v1")
    await mem.clear()
    assert await mem.get("k1") is None


# ── SharedMemory (uses InMemoryBackend since no Redis in test) ──


@pytest.mark.asyncio
async def test_shared_memory_set_get():
    sm = SharedMemory()
    await sm.set("score:c-1", 85)
    val = await sm.get("score:c-1")
    assert val == 85


@pytest.mark.asyncio
async def test_shared_memory_get_missing():
    sm = SharedMemory()
    assert await sm.get("nope") is None


@pytest.mark.asyncio
async def test_shared_memory_delete():
    sm = SharedMemory()
    await sm.set("k1", "val")
    assert await sm.delete("k1") is True
    assert await sm.get("k1") is None


@pytest.mark.asyncio
async def test_shared_memory_exists():
    sm = SharedMemory()
    await sm.set("k1", "val")
    assert await sm.exists("k1") is True
    await sm.delete("k1")
    assert await sm.exists("k1") is False


@pytest.mark.asyncio
async def test_shared_memory_keys():
    sm = SharedMemory()
    await sm.set("a:1", "x")
    await sm.set("a:2", "y")
    keys = await sm.keys("a:*")
    assert "a:1" in keys
    assert "a:2" in keys


@pytest.mark.asyncio
async def test_shared_memory_clear():
    sm = SharedMemory()
    await sm.set("k1", "val")
    await sm.clear()
    assert await sm.get("k1") is None
    assert await sm.exists("k1") is False


@pytest.mark.asyncio
async def test_shared_memory_ttl():
    sm = SharedMemory()
    await sm.set("k1", "val", ttl=2)
    assert await sm.ttl("k1") in (1, 2)


@pytest.mark.asyncio
async def test_shared_memory_json_roundtrip():
    sm = SharedMemory()
    obj = {"name": "张三", "scores": [85, 90], "active": True}
    await sm.set("candidate:1", obj)
    got = await sm.get("candidate:1")
    assert got == obj


@pytest.mark.asyncio
async def test_get_shared_memory_singleton():
    s1 = get_shared_memory()
    s2 = get_shared_memory()
    assert s1 is s2


# ── InMemoryBackend edge cases ──


@pytest.mark.asyncio
async def test_in_memory_set_removes_ttl_when_not_set():
    mem = InMemoryBackend()
    await mem.set("k1", b"v1", ttl=9999)
    assert "k1" in mem._ttls
    await mem.set("k1", b"v2")
    assert "k1" not in mem._ttls
    assert await mem.get("k1") == b"v2"


# ── RedisBackend (via mock) ──


def _mock_redis_client() -> MagicMock:
    """Build a mock Redis client for RedisBackend tests."""
    client = MagicMock()
    client.get = AsyncMock(return_value=b"mock_val")
    client.set = AsyncMock()
    client.setex = AsyncMock()
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=1)
    client.keys = AsyncMock(return_value=["k1", "k2"])
    client.expire = AsyncMock(return_value=True)
    client.ttl = AsyncMock(return_value=42)
    return client


@pytest.mark.asyncio
async def test_redis_backend_get():
    from app.agents.shared_memory import RedisBackend
    client = _mock_redis_client()
    rb = RedisBackend(client)
    val = await rb.get("k1")
    assert val is not None
    client.get.assert_awaited_once_with("k1")


@pytest.mark.asyncio
async def test_redis_backend_get_error():
    from app.agents.shared_memory import RedisBackend
    client = MagicMock()
    client.get = AsyncMock(side_effect=ConnectionError("no redis"))
    rb = RedisBackend(client)
    val = await rb.get("k1")
    assert val is None


@pytest.mark.asyncio
async def test_redis_backend_set_with_ttl():
    from app.agents.shared_memory import RedisBackend
    client = _mock_redis_client()
    rb = RedisBackend(client)
    await rb.set("k1", b"val", ttl=3600)
    client.setex.assert_awaited_once_with("k1", 3600, b"val")


@pytest.mark.asyncio
async def test_redis_backend_set_without_ttl():
    from app.agents.shared_memory import RedisBackend
    client = _mock_redis_client()
    rb = RedisBackend(client)
    await rb.set("k1", b"val")
    client.set.assert_awaited_once_with("k1", b"val")


@pytest.mark.asyncio
async def test_redis_backend_set_error():
    from app.agents.shared_memory import RedisBackend
    client = MagicMock()
    client.set = AsyncMock(side_effect=ConnectionError("no redis"))
    client.setex = AsyncMock(side_effect=ConnectionError("no redis"))
    rb = RedisBackend(client)
    await rb.set("k1", b"val")


@pytest.mark.asyncio
async def test_redis_backend_delete():
    from app.agents.shared_memory import RedisBackend
    client = _mock_redis_client()
    rb = RedisBackend(client)
    assert await rb.delete("k1") is True


@pytest.mark.asyncio
async def test_redis_backend_delete_error():
    from app.agents.shared_memory import RedisBackend
    client = MagicMock()
    client.delete = AsyncMock(side_effect=ConnectionError("no redis"))
    rb = RedisBackend(client)
    assert await rb.delete("k1") is False


@pytest.mark.asyncio
async def test_redis_backend_exists():
    from app.agents.shared_memory import RedisBackend
    client = _mock_redis_client()
    rb = RedisBackend(client)
    assert await rb.exists("k1") is True


@pytest.mark.asyncio
async def test_redis_backend_exists_error():
    from app.agents.shared_memory import RedisBackend
    client = MagicMock()
    client.exists = AsyncMock(side_effect=ConnectionError("no redis"))
    rb = RedisBackend(client)
    assert await rb.exists("k1") is False


@pytest.mark.asyncio
async def test_redis_backend_keys():
    from app.agents.shared_memory import RedisBackend
    client = _mock_redis_client()
    rb = RedisBackend(client)
    keys = await rb.keys("*")
    assert len(keys) == 2


@pytest.mark.asyncio
async def test_redis_backend_keys_error():
    from app.agents.shared_memory import RedisBackend
    client = MagicMock()
    client.keys = AsyncMock(side_effect=ConnectionError("no redis"))
    rb = RedisBackend(client)
    assert await rb.keys("*") == []


@pytest.mark.asyncio
async def test_redis_backend_expire():
    from app.agents.shared_memory import RedisBackend
    client = _mock_redis_client()
    rb = RedisBackend(client)
    assert await rb.expire("k1", 3600) is True


@pytest.mark.asyncio
async def test_redis_backend_expire_error():
    from app.agents.shared_memory import RedisBackend
    client = MagicMock()
    client.expire = AsyncMock(side_effect=ConnectionError("no redis"))
    rb = RedisBackend(client)
    assert await rb.expire("k1", 3600) is False


@pytest.mark.asyncio
async def test_redis_backend_ttl():
    from app.agents.shared_memory import RedisBackend
    client = _mock_redis_client()
    rb = RedisBackend(client)
    assert await rb.ttl("k1") == 42


@pytest.mark.asyncio
async def test_redis_backend_ttl_error():
    from app.agents.shared_memory import RedisBackend
    client = MagicMock()
    client.ttl = AsyncMock(side_effect=ConnectionError("no redis"))
    rb = RedisBackend(client)
    assert await rb.ttl("k1") == -2


@pytest.mark.asyncio
async def test_redis_backend_clear():
    from app.agents.shared_memory import RedisBackend
    client = _mock_redis_client()
    rb = RedisBackend(client)
    await rb.clear()


# ── SharedMemory edge cases (Redis mocked) ──


@pytest.mark.asyncio
async def test_shared_memory_ensure_redis_client_none():
    with patch("app.core.redis.get_redis", AsyncMock(return_value=None)):
        sm = SharedMemory()
        redis = await sm._ensure_redis()
        assert redis is None


@pytest.mark.asyncio
async def test_shared_memory_non_json_in_memory():
    sm = SharedMemory()
    await sm._in_memory.set("bin", b"not-json")
    val = await sm.get("bin")
    assert val == b"not-json"


@pytest.mark.asyncio
async def test_shared_memory_expire():
    sm = SharedMemory()
    await sm.set("k1", "val")
    assert await sm.expire("k1", 9999) is True
    assert await sm.expire("nope", 10) is False


@pytest.mark.asyncio
async def test_shared_memory_ttl_fallback():
    sm = SharedMemory()
    await sm.set("k1", "val", ttl=9999)
    ttl = await sm.ttl("k1")
    assert ttl > 0


@pytest.mark.asyncio
async def test_shared_memory_clear_redis_error():
    mock_client = MagicMock()
    mock_client.ping = AsyncMock()
    mock_client.keys = AsyncMock(side_effect=ConnectionError("redis down"))
    with patch("app.core.redis.get_redis", AsyncMock(return_value=mock_client)):
        sm = SharedMemory()
        await sm.clear()


@pytest.mark.asyncio
async def test_shared_memory_exists_with_redis():
    mock_client = MagicMock()
    mock_client.ping = AsyncMock()
    mock_client.exists = AsyncMock(return_value=1)
    mock_client.get = AsyncMock()
    with patch("app.core.redis.get_redis", AsyncMock(return_value=mock_client)):
        sm = SharedMemory()
        await sm.set("k1", "val")
        assert await sm.exists("k1") is True


@pytest.mark.asyncio
async def test_shared_memory_get_non_json_from_redis():
    mock_client = MagicMock()
    mock_client.ping = AsyncMock()
    mock_client.get = AsyncMock(return_value=b"raw-bytes-not-json")
    with patch("app.core.redis.get_redis", AsyncMock(return_value=mock_client)):
        sm = SharedMemory()
        val = await sm.get("raw_key")
        assert val == b"raw-bytes-not-json"


# ── Redis fallback edge cases (SharedMemory level) ──


@pytest.mark.asyncio
async def test_shared_memory_ttl_redis_returns_minus_one():
    mock_client = MagicMock()
    mock_client.ping = AsyncMock()
    mock_client.set = AsyncMock()
    mock_client.ttl = AsyncMock(return_value=-1)
    mock_client.get = AsyncMock()
    with patch("app.core.redis.get_redis", AsyncMock(return_value=mock_client)):
        sm = SharedMemory()
        await sm.set("k1", "val", ttl=None)
        assert await sm.ttl("k1") == -1


@pytest.mark.asyncio
async def test_shared_memory_clear_with_redis():
    mock_client = MagicMock()
    mock_client.ping = AsyncMock()
    mock_client.setex = AsyncMock()
    mock_client.keys = AsyncMock(return_value=["k1", "k2"])
    mock_client.delete = AsyncMock(return_value=1)
    mock_client.exists = AsyncMock(return_value=0)
    mock_client.get = AsyncMock()
    with patch("app.core.redis.get_redis", AsyncMock(return_value=mock_client)):
        sm = SharedMemory()
        await sm.set("k1", "val1")
        await sm.set("k2", "val2")
        await sm.clear()
        assert await sm.exists("k1") is False
        assert await sm.exists("k2") is False
        mock_client.delete.assert_any_await("k1")
        mock_client.delete.assert_any_await("k2")
