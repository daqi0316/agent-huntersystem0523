"""PlatformAdapter 抽象基类 + pkgutil 自动注册"""
from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CrawlResult(BaseModel):
    success: bool
    candidates: list[dict[str, Any]] = []
    error_message: str | None = None
    next_page_url: str | None = None
    rate_limit_info: dict[str, Any] | None = None
    captcha_triggered: bool = False
    proxy_used: str | None = None


class PlatformAdapter(ABC):
    """所有平台适配器的基类"""

    name: str = ""
    display_name: str = ""
    category: str = "job_board"
    anti_crawl_level: int = 1
    requires_login: bool = False
    use_stealth: bool = False

    # P3-7: 限频参数
    _MIN_RATE_LIMIT = 1
    _MAX_RATE_LIMIT = 30
    _BASE_RATE_LIMIT = 3
    _SUCCESS_WINDOW = 20
    _ERROR_WINDOW = 5
    _RATE_ADJUST_UP = 0.8
    _RATE_ADJUST_DOWN = 1.5

    def __init__(self, config: dict[str, Any] | None = None, proxy_pool=None):
        self.config = config or {}
        self.proxy_pool = proxy_pool
        self._consecutive_failures = 0
        self._current_rate_limit = self._BASE_RATE_LIMIT
        self._request_times: list[float] = []
        self._success_count = 0
        self._error_count = 0

    @abstractmethod
    async def search(self, keyword: str, **filters) -> CrawlResult:
        ...

    async def get_detail(self, url: str) -> CrawlResult:
        raise NotImplementedError

    async def parse_list(self, html: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def parse_detail(self, html: str) -> dict[str, Any]:
        raise NotImplementedError

    async def pre_search(self, keyword: str) -> None:
        pass

    async def post_search(self, result: CrawlResult) -> CrawlResult:
        return result

    def record_failure(self):
        self._consecutive_failures += 1

    def record_success(self):
        self._consecutive_failures = 0

    @property
    def health_status(self) -> str:
        if self._consecutive_failures >= 10:
            return "down"
        if self._consecutive_failures >= 3:
            return "degraded"
        return "healthy"

    # P3-7: 限频自动调整

    def record_request_result(self, success: bool, status_code: int | None = None, retry_after: int | None = None):
        import time
        now = time.monotonic()
        self._request_times.append(now)

        if retry_after and retry_after > 0:
            self._current_rate_limit = min(
                self._current_rate_limit * self._RATE_ADJUST_DOWN * (retry_after / 5),
                self._MAX_RATE_LIMIT,
            )
            return

        if success:
            self._success_count += 1
            if self._success_count >= self._SUCCESS_WINDOW:
                self._current_rate_limit = max(
                    self._current_rate_limit * self._RATE_ADJUST_UP,
                    self._MIN_RATE_LIMIT,
                )
                self._success_count = 0
        else:
            self._error_count += 1
            if self._error_count >= self._ERROR_WINDOW:
                self._current_rate_limit = min(
                    self._current_rate_limit * self._RATE_ADJUST_DOWN,
                    self._MAX_RATE_LIMIT,
                )
                self._error_count = 0

        self._clean_request_times()

    async def wait_for_rate_limit(self):
        import asyncio
        self._clean_request_times()
        if len(self._request_times) >= 2:
            elapsed = self._request_times[-1] - self._request_times[-2]
            wait = self._current_rate_limit - elapsed
            if wait > 0:
                await asyncio.sleep(wait)

    def _clean_request_times(self):
        import time
        now = time.monotonic()
        cutoff = now - 60
        self._request_times = [t for t in self._request_times if t > cutoff]


# ── 自动注册 ──

_ADAPTERS: dict[str, type[PlatformAdapter]] = {}


# ── 平台配置热加载（P5-6）──

_platform_config_cache: dict[str, dict[str, Any]] | None = None
_platform_cache_ts: float = 0


async def load_platform_config_from_db() -> dict[str, dict[str, Any]]:
    """从 DB 加载所有平台配置（带 10s 缓存）"""
    import time
    global _platform_config_cache, _platform_cache_ts
    now = time.monotonic()
    if _platform_config_cache is not None and now - _platform_cache_ts < 10:
        return _platform_config_cache

    try:
        from sqlalchemy import select
        from app.sourcing.models.platform_config import PlatformConfig
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(PlatformConfig))
            configs = result.scalars().all()

        cache: dict[str, dict[str, Any]] = {}
        for c in configs:
            cache[c.name] = {
                "rate_limit": c.rate_limit,
                "daily_quota": c.daily_quota_per_account,
                "enabled": c.enabled,
                "config": c.config or {},
                "anti_crawl_level": c.anti_crawl_level,
                "requires_login": c.requires_login,
            }
        _platform_config_cache = cache
        _platform_cache_ts = now
        return cache
    except Exception:
        logger.warning("Failed to load platform config from DB, using defaults", exc_info=True)
        return {}


async def invalidate_platform_config_cache():
    """使平台配置缓存失效（PATCH 后调用）"""
    global _platform_config_cache, _platform_cache_ts
    _platform_config_cache = None
    _platform_cache_ts = 0


def discover_adapters():
    """自动扫描 platforms/ 目录注册"""
    pkg_path = os.path.dirname(__file__)
    for _, name, _ in pkgutil.iter_modules([pkg_path]):
        if name.startswith("_") or name == "base":
            continue
        try:
            module = importlib.import_module(f".{name}", __package__)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type)
                        and issubclass(attr, PlatformAdapter)
                        and attr is not PlatformAdapter
                        and hasattr(attr, "name")
                        and attr.name):
                    _ADAPTERS[attr.name] = attr
                    logger.debug("Discovered adapter: %s", attr.name)
        except Exception as e:
            logger.warning("Failed to load adapter %s: %s", name, e)


def get_adapter(name: str) -> type[PlatformAdapter]:
    if name not in _ADAPTERS:
        raise ValueError(f"未知平台: {name}")
    return _ADAPTERS[name]


def list_adapters() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "display_name": cls.display_name,
            "category": cls.category,
            "anti_crawl_level": cls.anti_crawl_level,
            "requires_login": cls.requires_login,
        }
        for name, cls in _ADAPTERS.items()
    ]


# 模块导入时自动发现
discover_adapters()
