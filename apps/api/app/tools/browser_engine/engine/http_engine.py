"""
HTTP 直连引擎 — 第三优先级
适用于无反爬或低反爬平台（GitHub API、知乎、掘金等）
"""

from .. import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult
from typing import Optional
import httpx
import structlog

logger = structlog.get_logger()


class HTTPEngine(BaseBrowserEngine):
    """
    HTTP 直连引擎
    • 反爬等级: 1/5
    • 最高性能，最低资源消耗
    • 适用: GitHub API、知乎、掘金、CSDN
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/125.0.0.0 Safari/537.36",
            },
        )

    @property
    def engine_type(self) -> EngineType:
        return EngineType.HTTP

    @property
    def capability(self) -> EngineCapability:
        return EngineCapability(
            engine_type=self.engine_type,
            anti_crawl_level=1,
            supports_javascript=False,  # 无 JS 执行能力
            supports_cdp=False,
            supports_stealth=False,
            recaptcha_score=0.0,  # 无法过 reCAPTCHA
            startup_time_ms=0,  # 无启动耗时
            memory_mb=10,
        )

    async def health_check(self) -> EngineStatus:
        """HTTP 引擎始终可用"""
        return EngineStatus.AVAILABLE

    async def fetch_page(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> PageResult:
        """HTTP GET 请求"""
        try:
            response = await self._client.get(url, timeout=timeout / 1000)
            response.raise_for_status()

            return PageResult(
                success=True,
                html=response.text,
                url=str(response.url),
                engine_used=self.engine_type,
            )

        except Exception as e:
            logger.error("HTTP 请求失败", url=url, error=str(e))
            return PageResult(
                success=False,
                error_message=str(e),
                engine_used=self.engine_type,
            )

    async def execute_script(self, script: str) -> any:
        """HTTP 引擎不支持 JS 执行"""
        raise NotImplementedError("HTTP 引擎不支持 JavaScript 执行")

    async def close(self):
        """关闭 HTTP 客户端"""
        await self._client.aclose()
        logger.info("HTTP 引擎已关闭")
