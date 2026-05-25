"""Core module tests: Qdrant client + Redis client singletons."""

import importlib

import pytest


# ── Qdrant ─────────────────────────────────────────────────────────────────


class TestQdrantClient:
    """app.core.qdrant — get/close singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_qdrant_creates_client(self):
        """First call creates AsyncQdrantClient."""
        import app.core.qdrant

        importlib.reload(app.core.qdrant)
        app.core.qdrant.qdrant_client = None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.core.qdrant.AsyncQdrantClient", _MockAsyncQdrantClient)
            client = await app.core.qdrant.get_qdrant()
            assert client is not None
            assert app.core.qdrant.qdrant_client is client

        await _cleanup_qdrant()

    @pytest.mark.asyncio
    async def test_get_qdrant_returns_cached(self):
        """Second call returns same object."""
        import app.core.qdrant

        importlib.reload(app.core.qdrant)
        app.core.qdrant.qdrant_client = None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.core.qdrant.AsyncQdrantClient", _MockAsyncQdrantClient)
            client1 = await app.core.qdrant.get_qdrant()
            client2 = await app.core.qdrant.get_qdrant()
            assert client1 is client2

        await _cleanup_qdrant()

    @pytest.mark.asyncio
    async def test_close_qdrant_resets_client(self):
        """close_qdrant sets global to None."""
        import app.core.qdrant

        importlib.reload(app.core.qdrant)
        app.core.qdrant.qdrant_client = None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.core.qdrant.AsyncQdrantClient", _MockAsyncQdrantClient)
            client = await app.core.qdrant.get_qdrant()
            await app.core.qdrant.close_qdrant()
            assert app.core.qdrant.qdrant_client is None
            assert client.closed

        await _cleanup_qdrant()

    @pytest.mark.asyncio
    async def test_close_qdrant_when_already_none(self):
        """close_qdrant is safe when already None."""
        import app.core.qdrant

        importlib.reload(app.core.qdrant)
        app.core.qdrant.qdrant_client = None

        await app.core.qdrant.close_qdrant()
        assert app.core.qdrant.qdrant_client is None


# ── Redis ──────────────────────────────────────────────────────────────────


class TestRedisClient:
    """app.core.redis — get/close singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_redis_creates_client(self):
        """First call creates Redis from_url."""
        import app.core.redis as redis_mod

        importlib.reload(redis_mod)
        redis_mod.redis_client = None

        with pytest.MonkeyPatch.context() as mp:
            mock_instance = _MockRedisClient()
            mp.setattr("app.core.redis.redis_ai.from_url", _make_from_url(mock_instance))
            client = await redis_mod.get_redis()
            assert client is mock_instance

        await _cleanup_redis()

    @pytest.mark.asyncio
    async def test_get_redis_returns_cached(self):
        """Second call returns same object."""
        import app.core.redis as redis_mod

        importlib.reload(redis_mod)
        redis_mod.redis_client = None

        with pytest.MonkeyPatch.context() as mp:
            mock_instance = _MockRedisClient()
            mp.setattr("app.core.redis.redis_ai.from_url", _make_from_url(mock_instance))
            client1 = await redis_mod.get_redis()
            client2 = await redis_mod.get_redis()
            assert client1 is client2

        await _cleanup_redis()

    @pytest.mark.asyncio
    async def test_close_redis_resets_client(self):
        """close_redis sets global to None."""
        import app.core.redis as redis_mod

        importlib.reload(redis_mod)
        redis_mod.redis_client = None

        with pytest.MonkeyPatch.context() as mp:
            mock_instance = _MockRedisClient()
            mp.setattr("app.core.redis.redis_ai.from_url", _make_from_url(mock_instance))
            await redis_mod.get_redis()
            await redis_mod.close_redis()
            assert redis_mod.redis_client is None

        await _cleanup_redis()

    @pytest.mark.asyncio
    async def test_close_redis_when_already_none(self):
        """close_redis is safe when already None."""
        import app.core.redis as redis_mod

        importlib.reload(redis_mod)
        redis_mod.redis_client = None

        await redis_mod.close_redis()
        assert redis_mod.redis_client is None


# ── Helpers ────────────────────────────────────────────────────────────────


class _MockAsyncQdrantClient:
    """Minimal mock that tracks close()."""

    def __init__(self, **kwargs):
        self.closed = False
        self._kwargs = kwargs

    async def close(self):
        self.closed = True

    def __await__(self):
        return self.__aenter__().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


class _MockRedisClient:
    """Minimal mock for Redis client."""

    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


def _make_from_url(mock_instance):
    def from_url(url, **kwargs):
        return mock_instance

    return from_url


async def _cleanup_qdrant():
    import app.core.qdrant

    if app.core.qdrant.qdrant_client:
        await app.core.qdrant.qdrant_client.close()
    app.core.qdrant.qdrant_client = None


async def _cleanup_redis():
    import app.core.redis as redis_mod

    if redis_mod.redis_client:
        await redis_mod.redis_client.close()
    redis_mod.redis_client = None
