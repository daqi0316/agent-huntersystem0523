"""
浏览器引擎抽象层
支持 invisible_playwright (优先) + browser-use (备用) + HTTP (直连)
"""

from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger()


class EngineType(str, Enum):
    """引擎类型"""
    INVISIBLE_PLAYWRIGHT = "invisible_playwright"
    BROWSER_USE = "browser_use"
    HTTP = "http"
    # ★ 工程化扩展：预留未来引擎类型
    PLAYWRIGHT_DIRECT = "playwright_direct"
    SELENIUM = "selenium"


class EngineStatus(str, Enum):
    """引擎状态"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    # ★ 工程化扩展
    STARTING = "starting"
    COOLDOWN = "cooldown"
    MAINTENANCE = "maintenance"


@dataclass
class EngineCapability:
    """引擎能力描述"""
    engine_type: EngineType
    anti_crawl_level: int           # 1-5，反爬能力等级
    supports_javascript: bool
    supports_cdp: bool
    supports_stealth: bool
    recaptcha_score: float          # reCAPTCHA v3 预期得分
    startup_time_ms: int            # 启动耗时
    memory_mb: int                  # 内存占用
    # ★ 工程化扩展
    max_concurrent_pages: int = 1
    supports_screenshot: bool = True
    version: str = "1.0.0"


@dataclass
class PageResult:
    """页面采集结果"""
    success: bool
    html: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    screenshot: Optional[bytes] = None  # 调试用
    error_message: Optional[str] = None
    engine_used: Optional[EngineType] = None
    retry_count: int = 0
    # ★ 工程化扩展
    status_code: Optional[int] = None
    duration_ms: Optional[float] = None
    is_fallback: bool = False


class BaseBrowserEngine(ABC):
    """浏览器引擎基类"""

    def __init__(self, config: dict):
        self.config = config
        self._status = EngineStatus.AVAILABLE
        self._consecutive_failures = 0
        self._failure_threshold = 3  # 连续失败阈值

        # ★ 工程化扩展
        self._engine_name = self.__class__.__name__
        self._started_at: Optional[datetime] = None
        self._total_requests = 0
        self._total_success = 0
        self._total_failures = 0
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[datetime] = None

    # ===== 抽象接口（必须实现） =====

    @property
    @abstractmethod
    def engine_type(self) -> EngineType:
        pass

    @property
    @abstractmethod
    def capability(self) -> EngineCapability:
        pass

    @abstractmethod
    async def health_check(self) -> EngineStatus:
        """健康检查"""
        pass

    @abstractmethod
    async def fetch_page(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> PageResult:
        """获取页面内容，所有引擎统一接口"""
        pass

    @abstractmethod
    async def execute_script(self, script: str) -> Any:
        """执行 JavaScript"""
        pass

    @abstractmethod
    async def close(self):
        """关闭引擎，释放资源"""
        pass

    # ===== 通用方法 =====

    def record_failure(self):
        """记录失败"""
        self._consecutive_failures += 1
        self._total_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._status = EngineStatus.UNAVAILABLE
            logger.warning(
                f"引擎 {self.engine_type} 标记为不可用",
                failures=self._consecutive_failures,
            )

    def record_success(self):
        """记录成功"""
        self._consecutive_failures = 0
        self._total_success += 1
        self._status = EngineStatus.AVAILABLE

    @property
    def is_available(self) -> bool:
        return self._status != EngineStatus.UNAVAILABLE

    # ★ 工程化扩展方法

    async def warmup(self):
        """预热引擎 — 子类可选实现"""
        self._started_at = datetime.now(timezone.utc)

    async def reset(self):
        """重置引擎到初始状态"""
        await self.close()
        self._consecutive_failures = 0
        self._status = EngineStatus.AVAILABLE

    def get_stats(self) -> dict:
        """获取运行时统计"""
        uptime = 0
        if self._started_at:
            uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        return {
            "engine_type": self.engine_type.value,
            "status": self._status.value,
            "uptime_seconds": uptime,
            "total_requests": self._total_requests,
            "success_rate": (
                (self._total_success / max(self._total_requests, 1)) * 100
            ),
            "consecutive_failures": self._consecutive_failures,
            "last_error": self._last_error,
        }


# Convenience re-exports for engine implementations
__all__ = [
    "EngineType",
    "EngineStatus",
    "EngineCapability",
    "PageResult",
    "BaseBrowserEngine",
]
