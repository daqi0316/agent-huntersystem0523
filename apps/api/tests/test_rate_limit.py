"""Tests for RateLimitMiddleware and rate stores."""

import time as time_module

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.rate_limit import InMemoryRateStore, create_rate_limit_middleware, RedisStore


@pytest.fixture
def store():
    return InMemoryRateStore()


@pytest.mark.asyncio
class TestInMemoryRateStore:
    async def test_allow_within_limit(self, store):
        allowed, remaining = await store.check("test-key", limit=5, window=60)
        assert allowed is True
        assert remaining == 4

    async def test_block_when_exceeded(self, store):
        for i in range(3):
            await store.check("test-key", limit=3, window=60)

        allowed, remaining = await store.check("test-key", limit=3, window=60)
        assert allowed is False
        assert remaining == 0

    async def test_remaining_returns_correct_count(self, store):
        await store.check("test-key", limit=10, window=60)
        await store.check("test-key", limit=10, window=60)

        assert await store.remaining("test-key", limit=10, window=60) == 8

    async def test_remaining_returns_limit_when_empty(self, store):
        assert await store.remaining("new-key", limit=50, window=60) == 50

    async def test_reset_clears_bucket(self, store):
        await store.check("reset-key", limit=1, window=60)
        assert await store.remaining("reset-key", limit=1, window=60) == 0

        await store.reset("reset-key")
        assert await store.remaining("reset-key", limit=1, window=60) == 1

    async def test_old_entries_are_pruned(self, store):
        ts = time_module.monotonic()
        store._buckets["prune-key"] = [ts - 120, ts - 90]
        allowed, _ = await store.check("prune-key", limit=5, window=60)
        assert allowed is True


class TestRedisStore:
    """RedisStore tests with mocked Redis client."""

    @pytest.fixture
    def mock_redis(self):
        from unittest.mock import AsyncMock, MagicMock
        redis = MagicMock()

        pipe = MagicMock()
        pipe.incr = AsyncMock(return_value=pipe)
        pipe.ttl = AsyncMock(return_value=pipe)
        pipe.execute = AsyncMock(return_value=[1, -1])
        redis.pipeline.return_value = pipe

        redis.get = AsyncMock()
        redis.delete = AsyncMock()
        redis.expire = AsyncMock()
        return redis

    @pytest.fixture
    def rstore(self, mock_redis):
        return RedisStore(mock_redis)

    async def test_allow_within_limit(self, mock_redis, rstore):
        mock_redis.pipeline.return_value.execute.return_value = [1, -1]
        allowed, remaining = await rstore.check("k", limit=5, window=60)
        assert allowed is True
        assert remaining == 4

    async def test_block_when_exceeded(self, mock_redis, rstore):
        mock_redis.pipeline.return_value.execute.return_value = [11, -1]
        allowed, remaining = await rstore.check("k", limit=5, window=60)
        assert allowed is False
        assert remaining == 0

    async def test_remaining_returns_correct_count(self, mock_redis, rstore):
        mock_redis.get.return_value = "3"
        assert await rstore.remaining("k", limit=10, window=60) == 7

    async def test_remaining_returns_limit_when_empty(self, mock_redis, rstore):
        mock_redis.get.return_value = None
        assert await rstore.remaining("k", limit=50, window=60) == 50

    async def test_reset_clears_key(self, mock_redis, rstore):
        await rstore.reset("k")
        mock_redis.delete.assert_awaited_once_with("k")


class TestRateLimitMiddleware:

    @pytest.fixture
    def app(self):
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        app.middleware("http")(create_rate_limit_middleware(limit=3, window=60))

        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_requests_within_limit_succeed(self, client):
        for i in range(3):
            resp = client.get("/test")
            assert resp.status_code == 200, f"Request {i+1} failed: {resp.json()}"
            assert "X-RateLimit-Remaining" in resp.headers

    def test_exceeded_limit_returns_429(self, client):
        for i in range(3):
            client.get("/test")

        resp = client.get("/test")
        assert resp.status_code == 429
        data = resp.json()
        assert data["success"] is False
        assert "error" in data
        assert "Retry-After" in resp.headers

    def test_excluded_paths_are_not_limited(self, client):
        for i in range(10):
            resp = client.get("/health")
            assert resp.status_code == 200, f"Request {i+1} failed"
