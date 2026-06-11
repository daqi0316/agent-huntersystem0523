"""Tests for proxy_pool.py — 代理池管理"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sourcing.proxy_pool import ProxyPool, get_proxy_pool_health


class TestProxyPool:
    @pytest.fixture
    def pool_memory(self):
        """ProxyPool with in-memory backend (no Redis)."""
        return ProxyPool(redis=None)

    @pytest.fixture
    def pool_redis(self):
        """ProxyPool with mock Redis."""
        redis = AsyncMock()
        return ProxyPool(redis=redis)

    # ── get_proxy ──

    @pytest.mark.parametrize("platform,acl,expected_tier", [
        ("boss_zhipin", 0, "premium"),
        ("boss_zhipin", 3, "premium"),
        ("liepin", 5, "premium"),
        ("liepin", 3, "standard"),
        ("linkedin", 1, None),
        ("github", 0, None),
    ])
    async def test_get_proxy_tier_selection(self, platform, acl, expected_tier, pool_redis):
        pool_redis._acquire = AsyncMock(return_value="http://proxy:8080" if expected_tier else None)
        result = await pool_redis.get_proxy(platform, acl)
        if expected_tier:
            assert result == "http://proxy:8080"
        else:
            assert result is None

    async def test_get_proxy_premium_when_acl_4(self, pool_redis):
        pool_redis._acquire = AsyncMock(return_value="http://premium:3128")
        result = await pool_redis.get_proxy("liepin", 4)
        assert result == "http://premium:3128"

    # ── report_failure with Redis ──

    async def test_report_failure_redis_reduces_score(self, pool_redis):
        pool_redis.redis.zscore.return_value = 5.0
        await pool_redis.report_failure("http://proxy:8080", "liepin", "TIMEOUT")
        pool_redis.redis.zadd.assert_called()  # called for each tier

    async def test_report_failure_redis_evicts_below_threshold(self, pool_redis):
        pool_redis.redis.zscore.return_value = -9.0
        pool_redis.redis.zincrby.return_value = 1  # prevent default AsyncMock for else branch
        await pool_redis.report_failure("http://proxy:8080", "liepin", "CONNECTION_RESET")
        pool_redis.redis.zrem.assert_called()

    async def test_report_failure_redis_evicts_at_max_failures(self, pool_redis):
        pool_redis.redis.zscore.side_effect = [None, None, None]
        pool_redis.redis.zincrby.return_value = 5  # >= MAX_FAILURES
        await pool_redis.report_failure("http://proxy:8080", "liepin")
        pool_redis.redis.zrem.assert_called()

    # ── report_failure in-memory ──

    async def test_report_failure_memory_increases_failures(self, pool_memory):
        pool_memory._in_memory["premium"] = [{"url": "http://proxy:8080", "failures": 0, "quality_score": 0}]
        await pool_memory.report_failure("http://proxy:8080", "liepin")
        assert pool_memory._in_memory["premium"][0]["failures"] == 1

    async def test_report_failure_memory_evicts(self, pool_memory):
        pool_memory._in_memory["premium"] = [{"url": "http://proxy:8080", "failures": 0, "quality_score": -9}]
        await pool_memory.report_failure("http://proxy:8080", "liepin", "TIMEOUT")
        assert pool_memory._in_memory["premium"] == []

    # ── report_success ──

    async def test_report_success_redis_boosts(self, pool_redis):
        pool_redis.redis.zscore.side_effect = [5.0, None, None]  # only premium found, rest get None
        await pool_redis.report_success("http://proxy:8080", "liepin", latency_ms=100)
        pool_redis.redis.zadd.assert_called_once()

    async def test_report_success_memory(self, pool_memory):
        pool_memory._in_memory["premium"] = [{"url": "http://proxy:8080", "quality_score": 5}]
        await pool_memory.report_success("http://proxy:8080", "liepin", latency_ms=500)
        assert pool_memory._in_memory["premium"][0]["quality_score"] > 5

    # ── check_proxy_health ──

    async def test_check_proxy_health_success(self, pool_memory):
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_resp = MagicMock()
            mock_resp.is_success = True
            mock_instance.get.return_value = mock_resp

            result = await pool_memory.check_proxy_health("http://proxy:8080")
            assert result["alive"] is True
            assert result["latency_ms"] is not None

    async def test_check_proxy_health_failure(self, pool_memory):
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = Exception("Connection refused")

            result = await pool_memory.check_proxy_health("http://proxy:8080")
            assert result["alive"] is False
            assert result["error"] is not None

    # ── health_check ──

    async def test_health_check_redis(self, pool_redis):
        pool_redis.redis.zcard.return_value = 5
        pool_redis.redis.zrange.return_value = [("http://p1:8080", 0.0), ("http://p2:8080", -3.0)]
        result = await pool_redis.health_check()
        assert result["premium"] == 5
        assert "premium_high_quality" in result

    async def test_health_check_memory(self, pool_memory):
        pool_memory._in_memory["premium"] = [{"url": "http://p1:8080", "quality_score": 5}]
        pool_memory._in_memory["standard"] = []
        result = await pool_memory.health_check()
        assert result["premium"] == 1
        assert result["standard"] == 0

    # ── _acquire_from_redis ──

    async def test_acquire_from_redis_normal(self, pool_redis):
        pool_redis.redis.zcard.return_value = 10
        pool_redis.redis.zrange.return_value = [("http://p1:8080", 0.0), ("http://p2:8080", 0.0)]
        result = await pool_redis._acquire_from_redis("premium")
        assert result is not None
        assert result.startswith("http")

    async def test_acquire_from_redis_refill_when_low(self, pool_redis):
        pool_redis.redis.zcard.return_value = 2  # below REFILL_MIN (3)
        pool_redis.redis.zrange.return_value = [("http://p1:8080", 0.0)]
        pool_redis._fetch_proxies = AsyncMock()
        result = await pool_redis._acquire_from_redis("premium")
        assert result is not None
        pool_redis._fetch_proxies.assert_called_once_with("premium")

    async def test_acquire_from_redis_empty_after_refill(self, pool_redis):
        pool_redis.redis.zcard.side_effect = [2, 0]  # low, then after refill still empty
        pool_redis.redis.zrange.return_value = []
        pool_redis._fetch_proxies = AsyncMock()
        result = await pool_redis._acquire_from_redis("premium")
        assert result is None

    # ── _acquire_from_memory ──

    def test_acquire_from_memory_empty(self, pool_memory):
        result = pool_memory._acquire_from_memory("premium")
        assert result is None

    def test_acquire_from_memory_selects_lowest_failures(self, pool_memory):
        pool_memory._in_memory["premium"] = [
            {"url": "http://p1:8080", "failures": 0},
            {"url": "http://p2:8080", "failures": 3},
        ]
        result = pool_memory._acquire_from_memory("premium")
        assert result == "http://p1:8080"

    # ── _parse_proxy_response ──

    def test_parse_list_format(self, pool_memory):
        data = ["http://p1:8080", "http://p2:8080"]
        result = pool_memory._parse_proxy_response(data)
        assert result == ["http://p1:8080", "http://p2:8080"]

    def test_parse_dict_data_key(self, pool_memory):
        data = {"data": [{"ip": "1.2.3.4", "port": 8080}]}
        result = pool_memory._parse_proxy_response(data)
        assert result == ["http://1.2.3.4:8080"]

    def test_parse_dict_proxies_key(self, pool_memory):
        data = {"proxies": ["http://p1:8080"]}
        result = pool_memory._parse_proxy_response(data)
        assert result == ["http://p1:8080"]

    def test_parse_kv_format(self, pool_memory):
        data = {"proxy1": "http://p1:8080", "proxy2": "http://p2:8080"}
        result = pool_memory._parse_proxy_response(data)
        assert len(result) == 2

    def test_parse_empty(self, pool_memory):
        assert pool_memory._parse_proxy_response({}) == []
        assert pool_memory._parse_proxy_response(None) == []

    # ── run_health_check ──

    async def test_run_health_check_memory(self, pool_memory):
        pool_memory._in_memory["premium"] = [{"url": "http://p1:8080"}]
        pool_memory.check_proxy_health = AsyncMock(return_value={"alive": True, "latency_ms": 100})
        pool_memory._update_health_score = AsyncMock()

        details = await pool_memory.run_health_check()
        assert details["alive"] >= 1
        assert "by_tier" in details


class TestModuleLevel:
    async def test_get_proxy_pool_health(self):
        with patch("app.core.redis.get_redis", new_callable=AsyncMock) as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            mock_redis.zcard.return_value = 5
            mock_redis.zrange.return_value = []
            result = await get_proxy_pool_health()
            assert "premium" in result
