"""
invisible_playwright 引擎实现 — 第一优先级
高反爬平台主力引擎
"""

from .. import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult
from typing import Optional, Any
from invisible_playwright import InvisiblePlaywright
from concurrent.futures import ThreadPoolExecutor
import structlog
import asyncio

logger = structlog.get_logger()


class InvisiblePlaywrightEngine(BaseBrowserEngine):
    """
    invisible_playwright 引擎
    • reCAPTCHA v3: 0.90
    • 反爬等级: 5/5
    • 适用: BOSS直聘、猎聘、脉脉、LinkedIn
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._playwright: Optional[InvisiblePlaywright] = None
        self._browser = None
        self._page = None
        self._seed = config.get("seed")
        self._proxy = config.get("proxy")
        self._executor = ThreadPoolExecutor(max_workers=1)

    @property
    def engine_type(self) -> EngineType:
        return EngineType.INVISIBLE_PLAYWRIGHT

    @property
    def capability(self) -> EngineCapability:
        return EngineCapability(
            engine_type=self.engine_type,
            anti_crawl_level=5,
            supports_javascript=True,
            supports_cdp=False,
            supports_stealth=True,
            recaptcha_score=0.90,
            startup_time_ms=3000,
            memory_mb=400,
        )

    async def _sync_call(self, fn, *args, **kwargs):
        """所有 Playwright sync API 通过同一个线程执行"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: fn(*args, **kwargs),
        )

    async def _ensure_browser(self):
        if self._browser is None:
            logger.info("启动 invisible_playwright 引擎")

            self._playwright = InvisiblePlaywright(
                proxy=self._proxy,
                seed=self._seed,
                pin=self.config.get("pin", {}),
            )
            self._browser = await self._sync_call(self._playwright.__enter__)
            logger.info("invisible_playwright 引擎启动完成")

    async def health_check(self) -> EngineStatus:
        try:
            await self._ensure_browser()

            def _check():
                page = self._browser.new_page()
                page.goto("https://www.google.com", timeout=10000)
                title = page.title()
                page.close()
                return title

            title = await self._sync_call(_check)

            if "Google" in title:
                self.record_success()
                return EngineStatus.AVAILABLE
            return EngineStatus.DEGRADED

        except Exception as e:
            logger.error("invisible_playwright 健康检查失败", error=str(e))
            self.record_failure()
            return EngineStatus.UNAVAILABLE

    async def fetch_page(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> PageResult:
        try:
            await self._ensure_browser()

            def _fetch():
                page = self._browser.new_page()
                logger.info("invisible_playwright 开始导航", url=url)
                page.goto(url, wait_until="networkidle", timeout=timeout)
                if wait_for:
                    page.wait_for_selector(wait_for, timeout=timeout)
                html = page.content()
                title = page.title()
                current_url = page.url
                page.close()
                return current_url, title, html

            current_url, title, html = await self._sync_call(_fetch)
            self.record_success()

            return PageResult(
                success=True,
                html=html,
                url=current_url,
                title=title,
                engine_used=self.engine_type,
            )

        except Exception as e:
            logger.error("invisible_playwright 获取页面失败", url=url, error=str(e))
            self.record_failure()
            return PageResult(
                success=False,
                error_message=str(e),
                engine_used=self.engine_type,
            )

    async def execute_script(self, script: str) -> Any:
        if self._page:
            return await self._sync_call(self._page.evaluate, script)
        raise RuntimeError("无活动页面")

    async def close(self):
        if self._playwright:
            await self._sync_call(self._playwright.__exit__, None, None, None)
            self._browser = None
            self._playwright = None
            self._executor.shutdown(wait=False)
            logger.info("invisible_playwright 引擎已关闭")
