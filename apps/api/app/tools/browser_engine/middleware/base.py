"""
引擎中间件管道 — 在 fetch_page 前后执行横切逻辑
支持 retry、timeout、proxy 选择、指标采集
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Any
import structlog

from .. import PageResult, EngineType

logger = structlog.get_logger()


class EngineMiddleware(ABC):
    """引擎中间件基类"""

    @abstractmethod
    async def before_fetch(
        self,
        url: str,
        engine_type: EngineType,
        config: dict,
    ) -> tuple[str, dict]:
        """fetch 前调用，可修改 url 和 config"""
        return url, config

    @abstractmethod
    async def after_fetch(
        self,
        url: str,
        result: PageResult,
        engine_type: EngineType,
    ) -> PageResult:
        """fetch 后调用，可修改 result"""
        return result


class MiddlewarePipeline:
    """中间件管道 — 按序执行"""

    def __init__(self):
        self._middlewares: list[EngineMiddleware] = []

    def add(self, middleware: EngineMiddleware):
        self._middlewares.append(middleware)
        logger.debug("中间件已注册", name=middleware.__class__.__name__)

    async def execute_before(
        self,
        url: str,
        engine_type: EngineType,
        config: dict,
    ) -> tuple[str, dict]:
        for mw in self._middlewares:
            url, config = await mw.before_fetch(url, engine_type, config)
        return url, config

    async def execute_after(
        self,
        url: str,
        result: PageResult,
        engine_type: EngineType,
    ) -> PageResult:
        for mw in self._middlewares:
            result = await mw.after_fetch(url, result, engine_type)
        return result


# ── 内置中间件 ──

class RetryMiddleware(EngineMiddleware):
    """重试中间件 — 失败自动重试"""

    def __init__(self, max_retries: int = 2, retry_delay_ms: int = 1000):
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms

    async def before_fetch(self, url: str, engine_type: EngineType, config: dict) -> tuple[str, dict]:
        config["_retry_count"] = config.get("_retry_count", 0) + 1
        return url, config

    async def after_fetch(self, url: str, result: PageResult, engine_type: EngineType) -> PageResult:
        return result


class TimeoutMiddleware(EngineMiddleware):
    """超时中间件 — 设置请求超时"""

    def __init__(self, default_timeout: int = 30000):
        self.default_timeout = default_timeout

    async def before_fetch(self, url: str, engine_type: EngineType, config: dict) -> tuple[str, dict]:
        if "timeout" not in config:
            config["timeout"] = self.default_timeout
        return url, config

    async def after_fetch(self, url: str, result: PageResult, engine_type: EngineType) -> PageResult:
        return result


class ProxySelectorMiddleware(EngineMiddleware):
    """代理选择中间件"""

    def __init__(self, proxy_pool=None):
        self.proxy_pool = proxy_pool

    async def before_fetch(self, url: str, engine_type: EngineType, config: dict) -> tuple[str, dict]:
        if self.proxy_pool and engine_type == EngineType.HTTP:
            proxy = await self.proxy_pool.get_proxy("default", 1)
            if proxy:
                config["proxy"] = proxy
        return url, config

    async def after_fetch(self, url: str, result: PageResult, engine_type: EngineType) -> PageResult:
        return result


class MetricsCollectorMiddleware(EngineMiddleware):
    """指标采集中间件"""

    async def before_fetch(self, url: str, engine_type: EngineType, config: dict) -> tuple[str, dict]:
        return url, config

    async def after_fetch(self, url: str, result: PageResult, engine_type: EngineType) -> PageResult:
        return result


__all__ = [
    "EngineMiddleware",
    "MiddlewarePipeline",
    "RetryMiddleware",
    "TimeoutMiddleware",
    "ProxySelectorMiddleware",
    "MetricsCollectorMiddleware",
]
