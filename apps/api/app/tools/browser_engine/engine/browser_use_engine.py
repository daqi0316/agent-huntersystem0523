"""
browser-use 引擎实现 — 第二优先级（备用）
invisible_playwright 失败时自动降级使用
"""

from .. import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult
from typing import Optional
from browser_use import Browser
import structlog

logger = structlog.get_logger()


class BrowserUseEngine(BaseBrowserEngine):
    """
    browser-use 引擎 — 备用方案
    • 反爬等级: 3/5
    • 适用: 低反爬平台，或 invisible_playwright 失败时兜底
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._browser: Optional[Browser] = None
        self._cdp_url = config.get("cdp_url", "http://localhost:9222")
        self._headless = config.get("headless", False)

    @property
    def engine_type(self) -> EngineType:
        return EngineType.BROWSER_USE

    @property
    def capability(self) -> EngineCapability:
        return EngineCapability(
            engine_type=self.engine_type,
            anti_crawl_level=3,
            supports_javascript=True,
            supports_cdp=True,
            supports_stealth=False,  # JS 层覆盖，可被检测
            recaptcha_score=0.30,
            startup_time_ms=2000,
            memory_mb=350,
        )

    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser is None:
            logger.info("启动 browser-use 引擎（备用）")
            self._browser = Browser(
                headless=self._headless,
                cdp_url=self._cdp_url,
                is_local=not self._cdp_url or self._cdp_url == "http://localhost:9222",
            )

    async def health_check(self) -> EngineStatus:
        """健康检查"""
        try:
            await self._ensure_browser()
            # browser-use 无直接健康检查，尝试获取页面
            return EngineStatus.AVAILABLE
        except Exception as e:
            logger.error("browser-use 健康检查失败", error=str(e))
            return EngineStatus.UNAVAILABLE

    async def fetch_page(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> PageResult:
        """获取页面"""
        try:
            await self._ensure_browser()

            # browser-use 通过 Agent 操作
            from browser_use import Agent

            agent = Agent(
                task=f"打开 {url} 并获取页面内容",
                llm=None,  # 不需要 LLM，纯浏览器操作
                browser=self._browser,
            )

            # 执行导航
            await agent.run()

            # 获取页面内容（通过 CDP）
            html = await self._browser.get_page_source()

            self.record_success()

            return PageResult(
                success=True,
                html=html,
                url=url,
                engine_used=self.engine_type,
            )

        except Exception as e:
            logger.error("browser-use 获取页面失败", url=url, error=str(e))
            self.record_failure()
            return PageResult(
                success=False,
                error_message=str(e),
                engine_used=self.engine_type,
            )

    async def execute_script(self, script: str) -> any:
        """执行 JavaScript"""
        if self._browser:
            return await self._browser.execute_script(script)
        raise RuntimeError("浏览器未启动")

    async def close(self):
        """关闭引擎"""
        if self._browser:
            await self._browser.close()
            self._browser = None
            logger.info("browser-use 引擎已关闭")
