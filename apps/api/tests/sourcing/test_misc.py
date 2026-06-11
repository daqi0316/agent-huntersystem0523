"""Tests for misc sourcing modules: health_probe.py, ws_manager.py, config.py"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ════════════════════════════════════════════════
# health_probe.py
# ════════════════════════════════════════════════

class TestHealthProbe:
    @pytest.fixture(autouse=True)
    def setup(self):
        with patch("app.sourcing.health_probe.list_adapters") as self.mock_list:
            with patch("app.sourcing.health_probe.get_adapter") as self.mock_get:
                yield

    async def test_probe_platform_healthy(self):
        from app.sourcing.health_probe import probe_platform_health

        adapter_cls = MagicMock()
        adapter_cls.health_check_url = "https://example.com/health"
        self.mock_get.return_value = adapter_cls
        self.mock_list.return_value = [{"name": "test_platform"}]

        db = AsyncMock()
        config = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        db.execute.return_value = mock_result

        with patch("httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_client = AsyncMock()
            mock_client.get.return_value.status_code = 200
            mock_instance.__aenter__.return_value = mock_client
            mock_http.return_value = mock_instance

            results = await probe_platform_health(db)
            assert "test_platform" in results
            assert results["test_platform"]["status"] == "healthy"
            assert results["test_platform"]["http_status"] == 200
            assert config.health_status == "healthy"

    async def test_probe_platform_degraded(self):
        from app.sourcing.health_probe import probe_platform_health

        adapter_cls = MagicMock()
        adapter_cls.health_check_url = "https://example.com/health"
        self.mock_get.return_value = adapter_cls
        self.mock_list.return_value = [{"name": "test_platform"}]

        db = AsyncMock()
        config = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        db.execute.return_value = mock_result

        with patch("httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_client = AsyncMock()
            mock_client.get.return_value.status_code = 503
            mock_instance.__aenter__.return_value = mock_client
            mock_http.return_value = mock_instance

            results = await probe_platform_health(db)
            assert results["test_platform"]["status"] == "degraded"
            assert config.health_status == "degraded"

    async def test_probe_platform_down(self):
        from app.sourcing.health_probe import probe_platform_health

        self.mock_list.return_value = [{"name": "test_platform"}]
        adapter_cls = MagicMock()
        adapter_cls.health_check_url = "https://example.com/health"
        self.mock_get.return_value = adapter_cls

        db = AsyncMock()
        config = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        db.execute.return_value = mock_result

        with patch("httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Connection refused")
            mock_instance.__aenter__.return_value = mock_client
            mock_http.return_value = mock_instance

            results = await probe_platform_health(db)
            assert results["test_platform"]["status"] == "down"
            assert config.health_status == "down"
            db.commit.assert_called()

    async def test_probe_skips_without_health_check_url(self):
        from app.sourcing.health_probe import probe_platform_health

        adapter_cls = MagicMock()
        del adapter_cls.health_check_url  # no health_check_url attribute
        self.mock_get.return_value = adapter_cls
        self.mock_list.return_value = [{"name": "test_platform"}]

        db = AsyncMock()
        results = await probe_platform_health(db)
        assert "test_platform" not in results


# ════════════════════════════════════════════════
# ws_manager.py
# ════════════════════════════════════════════════

class TestTaskProgressManager:
    @pytest.fixture
    def manager(self):
        from app.sourcing.ws_manager import TaskProgressManager
        return TaskProgressManager()

    async def test_connect(self, manager):
        ws = AsyncMock()
        await manager.connect("task-1", ws)
        assert "task-1" in manager._connections
        assert len(manager._connections["task-1"]) == 1
        ws.accept.assert_called_once()

    async def test_disconnect(self, manager):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect("task-1", ws1)
        await manager.connect("task-1", ws2)
        assert len(manager._connections["task-1"]) == 2

        manager.disconnect("task-1", ws1)
        assert len(manager._connections["task-1"]) == 1
        assert manager._connections["task-1"][0] is ws2

    async def test_disconnect_cleans_up_empty_task(self, manager):
        ws = AsyncMock()
        await manager.connect("task-1", ws)
        manager.disconnect("task-1", ws)
        assert "task-1" not in manager._connections

    async def test_disconnect_nonexistent_task(self, manager):
        manager.disconnect("nonexistent", AsyncMock())  # should not raise

    async def test_push_progress(self, manager):
        ws = AsyncMock()
        await manager.connect("task-1", ws)

        await manager.push_progress("task-1", "platform_done", {"platform": "github"})
        ws.send_text.assert_called_once()
        payload = ws.send_text.call_args[0][0]
        assert "platform_done" in payload
        assert "github" in payload

    async def test_push_progress_handles_exception(self, manager):
        ws = AsyncMock()
        ws.send_text.side_effect = Exception("WS disconnected")
        await manager.connect("task-1", ws)

        await manager.push_progress("task-1", "progress", {})
        # Should not raise, should disconnect
        assert "task-1" not in manager._connections

    async def test_push_progress_no_clients(self, manager):
        # No connections for this task - should not raise
        await manager.push_progress("no-clients", "test", {})

    async def test_broadcast(self, manager):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect("task-1", ws1)
        await manager.connect("task-2", ws2)

        await manager.broadcast("system_event", {"msg": "all clients"})
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    async def test_broadcast_no_connections(self, manager):
        await manager.broadcast("test", {})

    def test_module_singleton(self):
        from app.sourcing.ws_manager import ws_manager, TaskProgressManager
        assert isinstance(ws_manager, TaskProgressManager)


# ════════════════════════════════════════════════
# config.py
# ════════════════════════════════════════════════

class TestSourcingSettings:
    def test_default_values(self):
        from app.sourcing.config import SourcingSettings
        settings = SourcingSettings()
        assert settings.playwright_headless is True
        assert settings.playwright_cdp_port == 9222
        assert settings.proxy_premium_url == ""
        assert settings.captcha_service == "none"
        assert settings.max_candidates_per_task == 500
        assert settings.default_rate_limit == 3
        assert settings.max_concurrent_tasks == 5
        assert settings.max_retries == 3
        assert settings.task_timeout_seconds == 3600
        assert settings.github_token == ""
        assert settings.ai_analysis_enabled is True
        assert settings.dedup_redis_ttl_days == 30
        assert settings.dedup_refresh_days == 7
        assert settings.redis_url == "redis://localhost:6379/2"
        assert settings.arq_redis_db == 2
        assert settings.arq_max_tries == 3
        assert settings.arq_job_timeout == 3600
        assert settings.arq_concurrency == 2

    def test_env_prefix(self):
        from app.sourcing.config import SourcingSettings
        with patch.dict("os.environ", {
            "SOURCING_PLAYWRIGHT_HEADLESS": "false",
            "SOURCING_GITHUB_TOKEN": "test-token",
        }, clear=True):
            settings = SourcingSettings()
            assert settings.playwright_headless is False
            assert settings.github_token == "test-token"

    def test_module_singleton(self):
        from app.sourcing.config import SourcingSettings, sourcing_settings
        assert isinstance(sourcing_settings, SourcingSettings)
