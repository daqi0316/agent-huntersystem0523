"""
引擎错误体系 — 分层可恢复错误
"""
from __future__ import annotations

from . import EngineType


class EngineError(Exception):
    """所有引擎错误的基类"""
    def __init__(self, message: str, engine_type: EngineType,
                 recoverable: bool = True, retry_delay: int = 0):
        self.engine_type = engine_type
        self.recoverable = recoverable
        self.retry_delay = retry_delay
        super().__init__(message)


class EngineUnavailableError(EngineError):
    """引擎不可用（资源耗尽/崩溃）"""
    def __init__(self, engine_type: EngineType, reason: str):
        super().__init__(f"{engine_type.value} 不可用: {reason}",
                        engine_type, recoverable=False)


class EngineTimeoutError(EngineError):
    """引擎操作超时"""
    def __init__(self, engine_type: EngineType, operation: str, timeout: int):
        super().__init__(f"{engine_type.value} {operation} 超时 {timeout}ms",
                        engine_type, recoverable=True, retry_delay=1_000)


class PageCrawlError(EngineError):
    """页面采集错误"""
    def __init__(self, engine_type: EngineType, url: str,
                 status_code: int, message: str):
        super().__init__(f"[{status_code}] {message}", engine_type)
        self.url = url
        self.status_code = status_code


__all__ = [
    "EngineError",
    "EngineUnavailableError",
    "EngineTimeoutError",
    "PageCrawlError",
]
