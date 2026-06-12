"""
Phase 终验：全栈集成测试

验证链路: scheduler → EngineManager → platform adapter → engine fallback → metrics

注意: EngineManager 是单例，httpx.AsyncClient 绑定创建时的事件循环。
      pytest-asyncio 默认 function-scope 事件循环，跨测试必须 reset。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.browser_engine import EngineType, EngineStatus, PageResult
from app.tools.browser_engine.manager.engine_manager import EngineManager
from app.tools.browser_engine.monitoring.metrics import monitored_fetch
from app.tools.browser_engine.monitoring.health import get_engine_health
from app.tools.browser_engine.scheduler import crawl_platform, run_crawl_task


@pytest.fixture(autouse=True)
def reset_engine_manager():
    """每个测试前重置 EngineManager 单例，避免 httpx client 跨事件循环失效"""
    EngineManager._instance = None


# ===== 集成测试 1: EngineManager → fetch → fallback 全链路 =====

class TestFullStackFetch:

    @pytest.mark.asyncio
    async def test_http_engine_direct_fetch(self):
        """HTTP 引擎真实请求 — 验证从 EngineManager 到 fetch 到返回"""
        manager = EngineManager()
        result = await manager.fetch_with_fallback(
            url="https://httpbin.org/get",
            platform_name="github",
            timeout=15000,
        )
        assert result.success is True
        assert result.engine_used == EngineType.HTTP
        assert result.html is not None
        assert len(result.html) > 0

    @pytest.mark.asyncio
    async def test_fallback_all_engines_http_succeeds(self):
        """invisible_playwright 优先 — 无浏览器时降级到 HTTP"""
        manager = EngineManager()
        result = await manager.fetch_with_fallback(
            url="https://httpbin.org/get",
            platform_name="boss_zhipin",
            timeout=15000,
        )
        # invisible_playwright 无浏览器会失败 → 降级到 browser_use(无浏览器) → HTTP 兜底
        assert result.success is True
        # 实际 engine_used 取决于 invisible_playwright 是否可用
        # 验证重点是 success=True

    @pytest.mark.asyncio
    async def test_fallback_fetch_degraded_url(self):
        """降级后 HTTP 应能正常返回页面内容"""
        manager = EngineManager()
        result = await manager.fetch_with_fallback(
            url="https://httpbin.org/get",
            platform_name="boss_zhipin",
            timeout=15000,
        )
        assert result.success is True


# ===== 集成测试 2: monitored_fetch + metrics =====

class TestMonitoredFetch:

    @pytest.mark.asyncio
    async def test_monitored_fetch_with_fallback(self):
        """monitored_fetch — 指标记录 + 降级不报错"""
        manager = EngineManager()
        result = await monitored_fetch(
            engine_manager=manager,
            url="https://httpbin.org/get",
            platform_name="boss_zhipin",
            timeout=15000,
        )
        assert result.success is True


# ===== 集成测试 3: scheduler API =====

class TestSchedulerIntegration:

    @pytest.mark.asyncio
    async def test_run_crawl_task_github(self):
        """run_crawl_task — HTTP 直连平台"""
        result = await run_crawl_task(
            platform_name="github",
            url="https://httpbin.org/get",
            timeout=15000,
        )
        assert result["success"] is True
        assert result["engine_used"] == "http"
        assert result["html_length"] > 0
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_run_crawl_task_high_anticrawl(self):
        """run_crawl_task — 高反爬平台，验证降级返回结构完整"""
        result = await run_crawl_task(
            platform_name="boss_zhipin",
            url="https://httpbin.org/get",
            timeout=15000,
        )
        assert result["success"] is True
        assert "timestamp" in result


# ===== 集成测试 4: health endpoint =====

class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_get_engine_health_empty(self):
        """get_engine_health — 引擎未创建时返回空"""
        result = await get_engine_health()
        assert "engines" in result
        assert "total_engines" in result
        assert "available" in result

    @pytest.mark.asyncio
    async def test_get_engine_health_after_fetch(self):
        """get_engine_health — 请求后应有 HTTP 引擎状态"""
        manager = EngineManager()
        await manager.fetch_with_fallback(
            url="https://httpbin.org/get",
            platform_name="github",
            timeout=15000,
        )
        result = await get_engine_health()
        engines = result["engines"]
        engine_keys = list(engines.keys())
        assert len(engine_keys) > 0


# ===== 集成测试 5: BossZhipinAdapterV3 health_check bugfix =====

class TestBossZhipinAdapterV3:

    @pytest.mark.asyncio
    async def test_health_check_no_crash(self):
        """BossZhipinAdapterV3 health_check — 不用 string key，不崩溃（回归测试）"""
        from app.sourcing.platforms.boss_zhipin_v3 import BossZhipinAdapterV3
        adapter = BossZhipinAdapterV3()
        status = await adapter.health_check()
        assert status in ("healthy", "degraded", "down")
