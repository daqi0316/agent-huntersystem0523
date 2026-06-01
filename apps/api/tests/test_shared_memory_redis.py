"""Tests for RedisBackend and SharedMemory via Redis path."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.shared_memory import RedisBackend, SharedMemory


def _make_mock_redis(**kwargs) -> AsyncMock:
    """Create a mock async Redis client with default success behaviors."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=kwargs.get("get", b'{"k":"v"}'))
    client.set = AsyncMock()
    client.setex = AsyncMock()
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=1)
    client.keys = AsyncMock(return_value=kwargs.get("keys", ["k1", "k2"]))
    client.expire = AsyncMock(return_value=True)
    client.ttl = AsyncMock(return_value=kwargs.get("ttl", 42))
    client.ping = AsyncMock()
    return client


# ── RedisBackend direct tests ──


@pytest.mark.asyncio
async def test_redis_backend_get_bytes():
    client = _make_mock_redis(get=b"hello")
    rb = RedisBackend(client)
    result = await rb.get("x")
    assert result == b"hello"
    client.get.assert_awaited_once_with("x")


@pytest.mark.asyncio
async def test_redis_backend_get_str():
    client = _make_mock_redis(get="hello")
    rb = RedisBackend(client)
    result = await rb.get("x")
    assert result == b"hello"


@pytest.mark.asyncio
async def test_redis_backend_get_none():
    client = _make_mock_redis(get=None)
    rb = RedisBackend(client)
    assert await rb.get("x") is None


@pytest.mark.asyncio
async def test_redis_backend_get_error():
    client = _make_mock_redis()
    client.get.side_effect = Exception("conn lost")
    rb = RedisBackend(client)
    assert await rb.get("x") is None


@pytest.mark.asyncio
async def test_redis_backend_set_with_ttl():
    client = _make_mock_redis()
    rb = RedisBackend(client)
    await rb.set("k", b"v", ttl=3600)
    client.setex.assert_awaited_once_with("k", 3600, b"v")


@pytest.mark.asyncio
async def test_redis_backend_set_without_ttl():
    client = _make_mock_redis()
    rb = RedisBackend(client)
    await rb.set("k", b"v")
    client.set.assert_awaited_once_with("k", b"v")


@pytest.mark.asyncio
async def test_redis_backend_set_error():
    client = _make_mock_redis()
    client.setex.side_effect = Exception("fail")
    rb = RedisBackend(client)
    await rb.set("k", b"v", ttl=10)  # should not raise


@pytest.mark.asyncio
async def test_redis_backend_delete_true():
    client = _make_mock_redis(delete=1)
    rb = RedisBackend(client)
    assert await rb.delete("k") is True
    client.delete.assert_awaited_once_with("k")


@pytest.mark.asyncio
async def test_redis_backend_delete_error():
    client = _make_mock_redis()
    client.delete.side_effect = Exception("fail")
    rb = RedisBackend(client)
    assert await rb.delete("k") is False


@pytest.mark.asyncio
async def test_redis_backend_exists_true():
    client = _make_mock_redis(exists=1)
    rb = RedisBackend(client)
    assert await rb.exists("k") is True


@pytest.mark.asyncio
async def test_redis_backend_exists_error():
    client = _make_mock_redis()
    client.exists.side_effect = Exception("fail")
    rb = RedisBackend(client)
    assert await rb.exists("k") is False


@pytest.mark.asyncio
async def test_redis_backend_keys():
    client = _make_mock_redis(keys=["a:1", "a:2"])
    rb = RedisBackend(client)
    result = await rb.keys("a:*")
    assert result == ["a:1", "a:2"]
    client.keys.assert_awaited_once_with("a:*")


@pytest.mark.asyncio
async def test_redis_backend_keys_error():
    client = _make_mock_redis()
    client.keys.side_effect = Exception("fail")
    rb = RedisBackend(client)
    assert await rb.keys() == []


@pytest.mark.asyncio
async def test_redis_backend_expire_true():
    client = _make_mock_redis(expire=True)
    rb = RedisBackend(client)
    assert await rb.expire("k", 10) is True
    client.expire.assert_awaited_once_with("k", 10)


@pytest.mark.asyncio
async def test_redis_backend_expire_error():
    client = _make_mock_redis()
    client.expire.side_effect = Exception("fail")
    rb = RedisBackend(client)
    assert await rb.expire("k", 10) is False


@pytest.mark.asyncio
async def test_redis_backend_ttl():
    client = _make_mock_redis(ttl=99)
    rb = RedisBackend(client)
    assert await rb.ttl("k") == 99
    client.ttl.assert_awaited_once_with("k")


@pytest.mark.asyncio
async def test_redis_backend_ttl_error():
    client = _make_mock_redis()
    client.ttl.side_effect = Exception("fail")
    rb = RedisBackend(client)
    assert await rb.ttl("k") == -2


@pytest.mark.asyncio
async def test_redis_backend_clear():
    rb = RedisBackend(_make_mock_redis())
    await rb.clear()  # no-op, should not raise


# ── SharedMemory via Redis path ──


@pytest.mark.asyncio
async def test_shared_memory_redis_get():
    client = _make_mock_redis(get=b'{"name":"test"}')
    with patch("app.core.redis.get_redis", return_value=client):
        sm = SharedMemory()
        result = await sm.get("k")
    assert result == {"name": "test"}


@pytest.mark.asyncio
async def test_shared_memory_redis_set():
    client = _make_mock_redis()
    with patch("app.core.redis.get_redis", return_value=client):
        sm = SharedMemory()
        await sm.set("k", {"score": 10}, ttl=60)
    client.setex.assert_awaited_once()
    args = client.setex.await_args
    assert args[0][0] == "k"
    assert args[0][1] == 60
    assert b"score" in args[0][2]


@pytest.mark.asyncio
async def test_shared_memory_redis_delete():
    client = _make_mock_redis(delete=1)
    with patch("app.core.redis.get_redis", return_value=client):
        sm = SharedMemory()
        result = await sm.delete("k")
    assert result is True
    client.delete.assert_awaited_once_with("k")


@pytest.mark.asyncio
async def test_shared_memory_redis_exists():
    client = _make_mock_redis(exists=1)
    with patch("app.core.redis.get_redis", return_value=client):
        sm = SharedMemory()
        assert await sm.exists("k") is True


@pytest.mark.asyncio
async def test_shared_memory_redis_keys():
    client = _make_mock_redis(keys=["a:1"])
    with patch("app.core.redis.get_redis", return_value=client):
        sm = SharedMemory()
        await sm.set("a:2", "x")  # in-memory set
        keys = await sm.keys("a:*")
    assert "a:1" in keys
    assert "a:2" in keys


@pytest.mark.asyncio
async def test_shared_memory_redis_expire():
    client = _make_mock_redis(expire=True)
    with patch("app.core.redis.get_redis", return_value=client):
        sm = SharedMemory()
        await sm.set("k", "v")
        result = await sm.expire("k", 30)
    assert result is True


@pytest.mark.asyncio
async def test_shared_memory_redis_ttl():
    client = _make_mock_redis(ttl=55)
    with patch("app.core.redis.get_redis", return_value=client):
        sm = SharedMemory()
        await sm.set("k", "v")
        assert await sm.ttl("k") == 55


@pytest.mark.asyncio
async def test_shared_memory_redis_unavailable():
    """When get_redis returns None, SharedMemory falls back to in-memory."""
    with patch("app.core.redis.get_redis", return_value=None):
        sm = SharedMemory()
        await sm.set("k", "val")
        assert await sm.get("k") == "val"
