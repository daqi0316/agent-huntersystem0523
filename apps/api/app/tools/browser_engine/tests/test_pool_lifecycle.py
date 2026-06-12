"""
EnginePool + EngineLifecycleManager 工程化测试
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.browser_engine import EngineType, EngineStatus, BaseBrowserEngine
from app.tools.browser_engine.manager.pool import EnginePool
from app.tools.browser_engine.manager.lifecycle import EngineLifecycleManager


# ===== Stub Engine =====

class StubEngine(BaseBrowserEngine):

    def __init__(self, engine_type: EngineType, config: dict | None = None):
        super().__init__(config or {})
        self._etype = engine_type
        self._closed = False

    @property
    def engine_type(self) -> EngineType:
        return self._etype

    @property
    def capability(self):
        from app.tools.browser_engine import EngineCapability
        return EngineCapability(
            engine_type=self._etype, anti_crawl_level=1,
            supports_javascript=False, supports_cdp=False,
            supports_stealth=False, recaptcha_score=0.0,
            startup_time_ms=0, memory_mb=0,
        )

    async def health_check(self) -> EngineStatus:
        return EngineStatus.AVAILABLE

    async def fetch_page(self, url, **kw):
        from app.tools.browser_engine import PageResult
        return PageResult(success=True, html="", url=url, engine_used=self._etype)

    async def execute_script(self, script):
        return None

    async def close(self):
        self._closed = True


# ===== EnginePool Tests =====

class TestEnginePool:

    def test_init(self):
        pool = EnginePool(pool_size=3)
        assert pool.pool_size == 3
        assert pool._pool == {}

    def test_default_pool_size(self):
        pool = EnginePool()
        assert pool.pool_size == 2

    def test_get_engines_unknown_type_returns_empty_list(self):
        pool = EnginePool()
        engines = pool.get_engines(EngineType.HTTP)
        assert engines == []

    @pytest.mark.asyncio
    async def test_release_adds_engine_to_pool(self):
        pool = EnginePool()
        engine = StubEngine(EngineType.HTTP)
        await pool.release(engine)
        assert pool._pool[EngineType.HTTP] == [engine]

    @pytest.mark.asyncio
    async def test_release_appends_to_existing_list(self):
        pool = EnginePool()
        e1 = StubEngine(EngineType.HTTP)
        e2 = StubEngine(EngineType.HTTP)
        await pool.release(e1)
        await pool.release(e2)
        assert len(pool._pool[EngineType.HTTP]) == 2

    @pytest.mark.asyncio
    async def test_release_separates_engine_types(self):
        pool = EnginePool()
        http = StubEngine(EngineType.HTTP)
        inv = StubEngine(EngineType.INVISIBLE_PLAYWRIGHT)
        await pool.release(http)
        await pool.release(inv)
        assert len(pool._pool[EngineType.HTTP]) == 1
        assert len(pool._pool[EngineType.INVISIBLE_PLAYWRIGHT]) == 1

    @pytest.mark.asyncio
    async def test_shutdown_all_closes_all_engines(self):
        pool = EnginePool()
        e1 = StubEngine(EngineType.HTTP)
        e2 = StubEngine(EngineType.INVISIBLE_PLAYWRIGHT)
        await pool.release(e1)
        await pool.release(e2)
        await pool.shutdown_all()
        assert e1._closed is True
        assert e2._closed is True
        assert pool._pool == {}

    @pytest.mark.asyncio
    async def test_shutdown_all_empty_does_not_raise(self):
        pool = EnginePool()
        await pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_shutdown_all_engine_error_does_not_propagate(self):
        pool = EnginePool()
        engine = StubEngine(EngineType.HTTP)
        engine.close = AsyncMock(side_effect=RuntimeError("boom"))
        await pool.release(engine)
        await pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_warmup_all_raises_not_implemented(self):
        pool = EnginePool()
        with pytest.raises(NotImplementedError):
            await pool.warmup_all()


# ===== EngineLifecycleManager Tests =====

class TestEngineLifecycleManager:

    @pytest.fixture
    def mock_manager(self):
        mgr = MagicMock()
        mgr._get_or_create_engine = MagicMock(return_value=StubEngine(EngineType.HTTP))
        mgr.close_all = AsyncMock()
        mgr.health_check_all = AsyncMock(return_value={})
        return mgr

    @pytest.mark.asyncio
    async def test_startup_initializes_engines_in_order(self, mock_manager):
        lifecycle = EngineLifecycleManager()
        lifecycle._manager = mock_manager
        await lifecycle.startup()
        calls = [c[0][0] for c in mock_manager._get_or_create_engine.call_args_list]
        assert calls == [EngineType.HTTP, EngineType.INVISIBLE_PLAYWRIGHT, EngineType.BROWSER_USE]

    @pytest.mark.asyncio
    async def test_startup_continues_on_engine_failure(self, mock_manager):
        lifecycle = EngineLifecycleManager()
        ok_engine = StubEngine(EngineType.HTTP)

        def side_effect(etype):
            if etype == EngineType.HTTP:
                return ok_engine
            raise RuntimeError("启动失败")

        mock_manager._get_or_create_engine = MagicMock(side_effect=side_effect)
        lifecycle._manager = mock_manager
        await lifecycle.startup()
        assert mock_manager._get_or_create_engine.call_count == 3

    @pytest.mark.asyncio
    async def test_shutdown_cancels_health_task(self, mock_manager):
        lifecycle = EngineLifecycleManager()
        lifecycle._manager = mock_manager

        async def never_ends():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(never_ends())
        lifecycle._health_task = task
        await lifecycle.shutdown()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_shutdown_calls_close_all(self, mock_manager):
        lifecycle = EngineLifecycleManager()
        lifecycle._manager = mock_manager

        async def never_ends():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(never_ends())
        lifecycle._health_task = task
        await lifecycle.shutdown()
        mock_manager.close_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_without_health_task(self, mock_manager):
        lifecycle = EngineLifecycleManager()
        lifecycle._manager = mock_manager
        await lifecycle.shutdown()
        mock_manager.close_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_check_loop_creates_task(self, mock_manager):
        lifecycle = EngineLifecycleManager()
        lifecycle._manager = mock_manager
        await lifecycle.health_check_loop(interval=9999)
        assert lifecycle._health_task is not None
        assert not lifecycle._health_task.done()
        lifecycle._health_task.cancel()
        try:
            await lifecycle._health_task
        except (asyncio.CancelledError, RuntimeError):
            pass

    @pytest.mark.asyncio
    async def test_health_loop_reports_unhealthy_engine(self, mock_manager):
        lifecycle = EngineLifecycleManager()
        mock_manager.health_check_all = AsyncMock(return_value={
            EngineType.INVISIBLE_PLAYWRIGHT: EngineStatus.UNAVAILABLE,
        })
        lifecycle._manager = mock_manager

        with patch.object(lifecycle, "_run_health_loop") as mocked_run:
            await lifecycle.health_check_loop(interval=9999)
            await asyncio.sleep(0.01)
            if lifecycle._health_task and not lifecycle._health_task.done():
                lifecycle._health_task.cancel()
                try:
                    await lifecycle._health_task
                except (asyncio.CancelledError, RuntimeError):
                    pass
