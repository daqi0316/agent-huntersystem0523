"""Tests for platforms/base.py — PlatformAdapter + 自动注册 + 配置缓存"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sourcing.platforms.base import (
    CrawlResult,
    PlatformAdapter,
    discover_adapters,
    get_adapter,
    invalidate_platform_config_cache,
    list_adapters,
    load_platform_config_from_db,
)


class TestCrawlResult:
    def test_default_values(self):
        r = CrawlResult(success=True)
        assert r.success is True
        assert r.candidates == []
        assert r.error_message is None
        assert r.next_page_url is None
        assert r.rate_limit_info is None
        assert r.captcha_triggered is False
        assert r.proxy_used is None

    def test_with_all_fields(self):
        r = CrawlResult(
            success=True,
            candidates=[{"name": "张三"}],
            error_message="ok",
            next_page_url="http://example.com/2",
            rate_limit_info={"remaining": 10},
            captcha_triggered=False,
            proxy_used="http://proxy:8080",
        )
        assert r.success is True
        assert r.candidates == [{"name": "张三"}]
        assert r.error_message == "ok"

    def test_failure_result(self):
        r = CrawlResult(success=False, error_message="rate_limited")
        assert r.success is False
        assert r.error_message == "rate_limited"


class TestPlatformAdapter:
    class ConcreteAdapter(PlatformAdapter):
        name = "test"
        display_name = "Test"
        anti_crawl_level = 2

        async def search(self, keyword: str, **filters) -> CrawlResult:
            return CrawlResult(success=True)

    @pytest.fixture
    def adapter(self):
        return self.ConcreteAdapter(config={"key": "val"}, proxy_pool=MagicMock())

    def test_init(self, adapter):
        assert adapter.config == {"key": "val"}
        assert adapter.proxy_pool is not None
        assert adapter._consecutive_failures == 0
        assert adapter._current_rate_limit == 3

    def test_health_status_healthy(self, adapter):
        assert adapter.health_status == "healthy"

    def test_health_status_degraded(self, adapter):
        for _ in range(5):
            adapter.record_failure()
        assert adapter.health_status == "degraded"

    def test_health_status_down(self, adapter):
        for _ in range(10):
            adapter.record_failure()
        assert adapter.health_status == "down"

    def test_record_success_resets_failures(self, adapter):
        adapter.record_failure()
        adapter.record_failure()
        adapter.record_success()
        assert adapter._consecutive_failures == 0

    def test_get_detail_not_implemented(self, adapter):
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.get_detail("http://example.com"))

    def test_parse_list_not_implemented(self, adapter):
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.parse_list("<html></html>"))

    def test_parse_detail_not_implemented(self, adapter):
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(adapter.parse_detail("<html></html>"))

    def test_pre_search_post_search_defaults(self, adapter):
        import asyncio
        asyncio.run(adapter.pre_search("test"))
        result = asyncio.run(adapter.post_search(CrawlResult(success=True)))
        assert result.success is True


class TestRateLimitAdjustment:
    class RateAdapter(PlatformAdapter):
        name = "ratetest"
        display_name = "RateTest"

        async def search(self, keyword: str, **filters) -> CrawlResult:
            return CrawlResult(success=True)

    @pytest.fixture
    def adapter(self):
        return self.RateAdapter()

    def test_initial_rate_limit(self, adapter):
        assert adapter._current_rate_limit == 3

    def test_retry_after_adjusts_up(self, adapter):
        adapter.record_request_result(success=False, retry_after=10)
        assert adapter._current_rate_limit > 3

    def test_success_window_adjusts_down(self, adapter):
        for _ in range(20):
            adapter.record_request_result(success=True)
        assert adapter._current_rate_limit < 3

    def test_error_window_adjusts_up(self, adapter):
        for _ in range(5):
            adapter.record_request_result(success=False)
        assert adapter._current_rate_limit > 3

    def test_rate_limit_clamped(self, adapter):
        # Should not go below _MIN_RATE_LIMIT (1)
        for _ in range(200):
            adapter.record_request_result(success=True)
        assert adapter._current_rate_limit >= 1


class TestAdapterRegistry:
    def test_discover_adapters_returns_known(self):
        adapters = list_adapters()
        names = [a["name"] for a in adapters]
        assert "liepin" in names
        assert "maimai" in names
        assert "linkedin" in names
        assert "github" in names

    def test_get_adapter_valid(self):
        from app.sourcing.platforms.liepin import LiepinAdapter
        cls = get_adapter("liepin")
        assert cls is LiepinAdapter

    def test_get_adapter_invalid_raises(self):
        with pytest.raises(ValueError, match="未知平台"):
            get_adapter("nonexistent_platform")

    def test_discovered_adapters_have_required_attrs(self):
        for info in list_adapters():
            assert info["name"]
            assert info["display_name"]
            assert info["category"]
            assert isinstance(info["anti_crawl_level"], int)
            assert isinstance(info["requires_login"], bool)


class TestPlatformConfigCache:
    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        await invalidate_platform_config_cache()
        yield

    async def test_load_empty_on_db_error(self):
        with patch("app.core.database.AsyncSessionLocal") as mock_session:
            mock_session.side_effect = Exception("DB error")
            result = await load_platform_config_from_db()
            assert result == {}

    async def _setup_db_mock(self):
        """Build mock chain for async with AsyncSessionLocal() as db: await db.execute(...)"""
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = []

        session = MagicMock()
        async def mock_execute(*args, **kwargs):
            return query_result
        session.execute = mock_execute

        cm = MagicMock()
        async def mock_aenter(*args):
            return session
        cm.__aenter__ = mock_aenter

        return cm, session, query_result

    async def test_cache_hit(self):
        # First call populates cache
        with patch("app.core.database.AsyncSessionLocal") as mock_session:
            cm, _, _ = await self._setup_db_mock()
            mock_session.return_value = cm

            result1 = await load_platform_config_from_db()

        # Second call should use cache (no DB call)
        with patch("app.core.database.AsyncSessionLocal") as mock_session2:
            result2 = await load_platform_config_from_db()
            mock_session2.assert_not_called()

    async def test_cache_expiry(self):
        with patch("app.core.database.AsyncSessionLocal") as mock_session:
            cm, _, _ = await self._setup_db_mock()
            mock_session.return_value = cm

            result1 = await load_platform_config_from_db()

            # Manually expire cache by setting timestamp to 0
            import app.sourcing.platforms.base as base_mod
            base_mod._platform_cache_ts = 0

            # Third call should hit DB again
            with patch("app.core.database.AsyncSessionLocal") as mock_session2:
                cm2, _, _ = await self._setup_db_mock()
                mock_session2.return_value = cm2
                result2 = await load_platform_config_from_db()
                assert mock_session2.called

    async def test_invalidation(self):
        import app.sourcing.platforms.base as base_mod
        base_mod._platform_config_cache = {"test": {}}
        base_mod._platform_cache_ts = 12345.0
        await invalidate_platform_config_cache()
        assert base_mod._platform_config_cache is None
        assert base_mod._platform_cache_ts == 0
