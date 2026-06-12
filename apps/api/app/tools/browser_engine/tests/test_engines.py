"""
浏览器引擎 — 单元测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.browser_engine import (
    EngineType, EngineStatus, EngineCapability, PageResult, BaseBrowserEngine,
)
from app.tools.browser_engine.errors import (
    EngineError, EngineUnavailableError, EngineTimeoutError, PageCrawlError,
)
from app.tools.browser_engine.engine.http_engine import HTTPEngine
from app.tools.browser_engine.engine.invisible_engine import InvisiblePlaywrightEngine
from app.tools.browser_engine.engine.browser_use_engine import BrowserUseEngine
from app.tools.browser_engine.manager.engine_manager import (
    EngineManager, EngineFallbackChain, PLATFORM_ENGINE_MAP,
)
from app.tools.browser_engine.config import (
    ENGINE_MANAGER_CONFIG, EngineManagerSettings,
)


# ===== EngineType / EngineStatus / EngineCapability =====

class TestEngineTypes:
    def test_engine_type_values(self):
        assert EngineType.INVISIBLE_PLAYWRIGHT.value == "invisible_playwright"
        assert EngineType.BROWSER_USE.value == "browser_use"
        assert EngineType.HTTP.value == "http"

    def test_engine_status_values(self):
        assert EngineStatus.AVAILABLE.value == "available"
        assert EngineStatus.UNAVAILABLE.value == "unavailable"

    def test_engine_capability_defaults(self):
        cap = EngineCapability(
            engine_type=EngineType.HTTP,
            anti_crawl_level=1,
            supports_javascript=False,
            supports_cdp=False,
            supports_stealth=False,
            recaptcha_score=0.0,
            startup_time_ms=0,
            memory_mb=10,
        )
        assert cap.max_concurrent_pages == 1
        assert cap.supports_screenshot is True
        assert cap.version == "1.0.0"


# ===== Error Hierarchy =====

class TestErrors:
    def test_base_engine_error(self):
        err = EngineError("test", EngineType.HTTP, recoverable=True, retry_delay=1000)
        assert err.engine_type == EngineType.HTTP
        assert err.recoverable is True
        assert err.retry_delay == 1000

    def test_engine_unavailable_error(self):
        err = EngineUnavailableError(EngineType.INVISIBLE_PLAYWRIGHT, "崩溃")
        assert err.recoverable is False
        assert "不可用" in str(err)

    def test_engine_timeout_error(self):
        err = EngineTimeoutError(EngineType.BROWSER_USE, "导航", 30000)
        assert err.recoverable is True
        assert "超时" in str(err)

    def test_page_crawl_error(self):
        err = PageCrawlError(EngineType.HTTP, "https://example.com", 403, "Forbidden")
        assert err.status_code == 403
        assert "[403]" in str(err)


# ===== BaseBrowserEngine =====

class _ConcreteTestEngine(BaseBrowserEngine):
    """Concrete engine subclass for testing base class methods"""
    @property
    def engine_type(self) -> EngineType:
        return EngineType.HTTP

    @property
    def capability(self) -> EngineCapability:
        return EngineCapability(
            engine_type=self.engine_type, anti_crawl_level=1,
            supports_javascript=False, supports_cdp=False, supports_stealth=False,
            recaptcha_score=0.0, startup_time_ms=0, memory_mb=10,
        )

    async def health_check(self) -> EngineStatus:
        return self._status

    async def fetch_page(self, url: str, wait_for=None, timeout=30000) -> PageResult:
        return PageResult(success=True)

    async def execute_script(self, script: str):
        raise NotImplementedError

    async def close(self):
        pass


class TestBaseBrowserEngine:
    def test_record_failure_triggers_unavailable(self):
        engine = _ConcreteTestEngine({})
        engine._failure_threshold = 2
        engine.record_failure()
        assert engine._status == EngineStatus.AVAILABLE
        engine.record_failure()
        assert engine._status == EngineStatus.UNAVAILABLE
        assert engine.is_available is False

    def test_record_success_resets_failures(self):
        engine = _ConcreteTestEngine({})
        engine._consecutive_failures = 3
        engine._status = EngineStatus.UNAVAILABLE
        engine.record_success()
        assert engine._consecutive_failures == 0
        assert engine._status == EngineStatus.AVAILABLE

    def test_get_stats(self):
        engine = _ConcreteTestEngine({})
        engine._total_requests = 10
        engine._total_success = 7
        stats = engine.get_stats()
        assert stats["engine_type"] == "http"
        assert stats["success_rate"] == 70.0
        assert stats["consecutive_failures"] == 0

    @pytest.mark.asyncio
    async def test_warmup_sets_started_at(self):
        engine = _ConcreteTestEngine({})
        await engine.warmup()
        assert engine._started_at is not None

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        engine = _ConcreteTestEngine({})
        await engine.close()
        engine._status = EngineStatus.UNAVAILABLE
        engine._consecutive_failures = 5
        await engine.reset()
        assert engine._status == EngineStatus.AVAILABLE
        assert engine._consecutive_failures == 0


# ===== HTTP Engine =====

class TestHTTPEngine:
    @pytest.mark.asyncio
    async def test_health_check_always_available(self):
        engine = HTTPEngine({"http": {}})
        status = await engine.health_check()
        assert status == EngineStatus.AVAILABLE

    @pytest.mark.asyncio
    async def test_engine_type(self):
        engine = HTTPEngine({"http": {}})
        assert engine.engine_type == EngineType.HTTP

    @pytest.mark.asyncio
    async def test_capability(self):
        engine = HTTPEngine({"http": {}})
        cap = engine.capability
        assert cap.anti_crawl_level == 1
        assert cap.supports_javascript is False

    @pytest.mark.asyncio
    async def test_execute_script_raises(self):
        engine = HTTPEngine({"http": {}})
        with pytest.raises(NotImplementedError):
            await engine.execute_script("test")

    @pytest.mark.asyncio
    async def test_close_cleans_up(self):
        engine = HTTPEngine({"http": {}})
        engine._client = AsyncMock()
        await engine.close()
        engine._client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        engine = HTTPEngine({"http": {}})
        engine._client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<html>ok</html>"
        mock_response.url = "https://example.com"
        mock_response.raise_for_status = MagicMock()
        engine._client.get = AsyncMock(return_value=mock_response)

        result = await engine.fetch_page("https://example.com")
        assert result.success is True
        assert result.html == "<html>ok</html>"

    @pytest.mark.asyncio
    async def test_fetch_failure(self):
        engine = HTTPEngine({"http": {}})
        engine._client = AsyncMock()
        engine._client.get = AsyncMock(side_effect=Exception("connection error"))

        result = await engine.fetch_page("https://example.com")
        assert result.success is False
        assert "connection error" in result.error_message


# ===== InvisiblePlaywright Engine =====

class TestInvisiblePlaywrightEngine:
    @pytest.mark.asyncio
    async def test_engine_type(self):
        engine = InvisiblePlaywrightEngine({"seed": None})
        assert engine.engine_type == EngineType.INVISIBLE_PLAYWRIGHT

    @pytest.mark.asyncio
    async def test_capability(self):
        engine = InvisiblePlaywrightEngine({"seed": None})
        cap = engine.capability
        assert cap.anti_crawl_level == 5
        assert cap.recaptcha_score == 0.90
        assert cap.supports_stealth is True

    @pytest.mark.asyncio
    async def test_health_check_returns_unavailable_when_no_browser(self):
        engine = InvisiblePlaywrightEngine({"seed": None})
        status = await engine.health_check()
        assert status == EngineStatus.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self):
        engine = InvisiblePlaywrightEngine({"seed": None})
        await engine.close()  # should not raise


# ===== BrowserUse Engine =====

class TestBrowserUseEngine:
    @pytest.mark.asyncio
    async def test_engine_type(self):
        engine = BrowserUseEngine({"headless": True})
        assert engine.engine_type == EngineType.BROWSER_USE

    @pytest.mark.asyncio
    async def test_capability(self):
        engine = BrowserUseEngine({"headless": True})
        cap = engine.capability
        assert cap.anti_crawl_level == 3
        assert cap.recaptcha_score == 0.30

    @pytest.mark.asyncio
    async def test_health_check_returns_available_by_default(self):
        engine = BrowserUseEngine({"headless": True})
        status = await engine.health_check()
        assert status == EngineStatus.AVAILABLE

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self):
        engine = BrowserUseEngine({"headless": True})
        await engine.close()  # should not raise


# ===== EngineManager =====

class TestEngineManager:
    def setup_method(self):
        EngineManager._instance = None

    def test_singleton(self):
        m1 = EngineManager()
        m2 = EngineManager()
        assert m1 is m2

    def test_get_preferred_engine_maps_boss_zhipin(self):
        manager = EngineManager()
        assert manager.get_preferred_engine("boss_zhipin") == EngineType.INVISIBLE_PLAYWRIGHT

    def test_get_preferred_engine_default(self):
        manager = EngineManager()
        assert manager.get_preferred_engine("unknown_platform") == EngineType.INVISIBLE_PLAYWRIGHT

    def test_get_preferred_engine_http(self):
        manager = EngineManager()
        assert manager.get_preferred_engine("github") == EngineType.HTTP

    @pytest.mark.asyncio
    async def test_fetch_with_fallback_uses_preferred_engine(self):
        manager = EngineManager()
        # invisible_playwright 为首选引擎，应当被优先使用
        result = await manager.fetch_with_fallback(
            url="https://example.com",
            platform_name="boss_zhipin",
        )
        # 首选引擎获取成功
        assert result.success is True
        assert result.engine_used == EngineType.INVISIBLE_PLAYWRIGHT

    @pytest.mark.asyncio
    async def test_health_check_all_empty(self):
        manager = EngineManager()
        results = await manager.health_check_all()
        assert results == {}

    @pytest.mark.asyncio
    async def test_close_all_empty(self):
        manager = EngineManager()
        await manager.close_all()  # should not raise

    def test_reset(self):
        manager = EngineManager()
        manager.reset()
        assert EngineManager._instance is None


# ===== Config =====

class TestConfig:
    def test_engine_manager_config_structure(self):
        assert "invisible_playwright" in ENGINE_MANAGER_CONFIG
        assert "browser_use" in ENGINE_MANAGER_CONFIG
        assert "http" in ENGINE_MANAGER_CONFIG

    def test_pydantic_settings_defaults(self):
        settings = EngineManagerSettings()
        assert settings.invisible_playwright.pool_size == 2
        assert settings.browser_use.headless is False
        assert settings.http.timeout == 30.0

    def test_pydantic_settings_custom(self):
        settings = EngineManagerSettings(
            invisible_playwright={"pool_size": 5},
            browser_use={"headless": True},
        )
        assert settings.invisible_playwright.pool_size == 5
        assert settings.browser_use.headless is True


# ===== Helpers =====

def _create_mock_engine() -> BaseBrowserEngine:
    """创建 mock 引擎用于测试基类方法"""
    engine = MagicMock(spec=BaseBrowserEngine)
    engine.engine_type = EngineType.HTTP
    engine._status = EngineStatus.AVAILABLE
    engine._consecutive_failures = 0
    engine._failure_threshold = 3
    engine._started_at = None
    engine._total_requests = 0
    engine._total_success = 0
    engine._total_failures = 0
    engine._last_error = None
    engine._last_error_at = None

    # Attach real methods
    import types
    for method_name in ["record_failure", "record_success", "reset", "get_stats"]:
        method = getattr(BaseBrowserEngine, method_name)
        if isinstance(method, types.FunctionType):
            setattr(engine, method_name, method.__get__(engine, BaseBrowserEngine))

    warmup = getattr(BaseBrowserEngine, "warmup")
    setattr(engine, "warmup", warmup.__get__(engine, BaseBrowserEngine))

    return engine
