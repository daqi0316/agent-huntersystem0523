"""Tests for RateLimitMiddleware and InMemoryRateStore."""

import time as time_module

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.rate_limit import InMemoryRateStore, RateLimitMiddleware


@pytest.fixture
def store():
    return InMemoryRateStore()


class TestInMemoryRateStore:
    def test_allow_within_limit(self, store):
        allowed, remaining = store.check("test-key", limit=5, window=60)
        assert allowed is True
        assert remaining == 4

    def test_block_when_exceeded(self, store):
        for i in range(3):
            store.check("test-key", limit=3, window=60)

        allowed, remaining = store.check("test-key", limit=3, window=60)
        assert allowed is False
        assert remaining == 0

    def test_remaining_returns_correct_count(self, store):
        store.check("test-key", limit=10, window=60)
        store.check("test-key", limit=10, window=60)

        assert store.remaining("test-key", limit=10, window=60) == 8

    def test_remaining_returns_limit_when_empty(self, store):
        assert store.remaining("new-key", limit=50, window=60) == 50

    def test_reset_clears_bucket(self, store):
        store.check("reset-key", limit=1, window=60)
        assert store.remaining("reset-key", limit=1, window=60) == 0

        store.reset("reset-key")
        assert store.remaining("reset-key", limit=1, window=60) == 1

    def test_old_entries_are_pruned(self, store):
        ts = time_module.monotonic()
        # Simulate entries older than the window
        store._buckets["prune-key"] = [ts - 120, ts - 90]
        allowed, _ = store.check("prune-key", limit=5, window=60)
        # Old entries should be pruned, leaving 0, so this should succeed
        assert allowed is True


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

        app.add_middleware(RateLimitMiddleware, limit=3, window=60)

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
        # Use up the 3 allowed requests
        for i in range(3):
            client.get("/test")

        # 4th request should be blocked
        resp = client.get("/test")
        assert resp.status_code == 429
        data = resp.json()
        assert data["success"] is False
        assert "error" in data
        assert "Retry-After" in resp.headers

    def test_excluded_paths_are_not_limited(self, client):
        """/health endpoint should not be rate limited."""
        for i in range(10):
            resp = client.get("/health")
            assert resp.status_code == 200, f"Request {i+1} failed"
