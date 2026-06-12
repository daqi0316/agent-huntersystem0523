"""
插件系统 — 引擎插件基类 + 注册表
可扩展性基础设施，支持第三方开发者编写引擎行为插件
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import structlog

from .. import PageResult, EngineType

logger = structlog.get_logger()


class EnginePlugin(ABC):
    """引擎插件基类"""

    name: str = ""
    version: str = "1.0.0"
    description: str = ""

    @abstractmethod
    async def on_fetch_start(self, url: str, engine_type: EngineType) -> dict | None:
        """fetch 开始时调用，返回额外配置"""
        return None

    @abstractmethod
    async def on_fetch_complete(self, url: str, result: PageResult, engine_type: EngineType):
        """fetch 完成时调用"""
        pass

    @abstractmethod
    async def on_error(self, url: str, error: Exception, engine_type: EngineType):
        """fetch 出错时调用"""
        pass


class PluginRegistry:
    """插件注册表"""

    _plugins: dict[str, EnginePlugin] = {}

    @classmethod
    def register(cls, plugin: EnginePlugin):
        if plugin.name in cls._plugins:
            logger.warning("插件已存在，将被覆盖", name=plugin.name)
        cls._plugins[plugin.name] = plugin
        logger.info("插件已注册", name=plugin.name, version=plugin.version)

    @classmethod
    def get(cls, name: str) -> EnginePlugin | None:
        return cls._plugins.get(name)

    @classmethod
    def list_plugins(cls) -> list[dict]:
        return [
            {"name": p.name, "version": p.version, "description": p.description}
            for p in cls._plugins.values()
        ]

    @classmethod
    def unregister(cls, name: str):
        cls._plugins.pop(name, None)

    @classmethod
    def clear(cls):
        cls._plugins.clear()


# ── 内置插件 ──

class ScreenshotCapturePlugin(EnginePlugin):
    """调试截图插件 — fetch 完成后截取页面截图"""

    name = "screenshot_capture"
    version = "1.0.0"
    description = "采集页面时自动截取调试截图"

    def __init__(self, output_dir: str = "/tmp/engine-screenshots"):
        self.output_dir = output_dir

    async def on_fetch_start(self, url: str, engine_type: EngineType) -> dict | None:
        return {"capture_screenshot": True}

    async def on_fetch_complete(self, url: str, result: PageResult, engine_type: EngineType):
        if result.screenshot:
            import os
            import hashlib
            os.makedirs(self.output_dir, exist_ok=True)
            filename = f"{hashlib.md5(url.encode()).hexdigest()}.png"
            path = os.path.join(self.output_dir, filename)
            with open(path, "wb") as f:
                f.write(result.screenshot)
            logger.info("截图已保存", path=path, url=url)

    async def on_error(self, url: str, error: Exception, engine_type: EngineType):
        pass


class RequestRecorderPlugin(EnginePlugin):
    """请求录制插件 — 记录所有 fetch 请求"""

    name = "request_recorder"
    version = "1.0.0"
    description = "记录所有引擎请求的 URL、耗时、结果"

    def __init__(self):
        self.records: list[dict] = []

    async def on_fetch_start(self, url: str, engine_type: EngineType) -> dict | None:
        import time
        self._current_start = time.monotonic()
        return None

    async def on_fetch_complete(self, url: str, result: PageResult, engine_type: EngineType):
        import time
        duration = time.monotonic() - getattr(self, "_current_start", time.monotonic())
        self.records.append({
            "url": url,
            "engine": engine_type.value,
            "success": result.success,
            "duration_ms": duration * 1000,
        })

    async def on_error(self, url: str, error: Exception, engine_type: EngineType):
        import time
        duration = time.monotonic() - getattr(self, "_current_start", time.monotonic())
        self.records.append({
            "url": url,
            "engine": engine_type.value,
            "success": False,
            "duration_ms": duration * 1000,
            "error": str(error),
        })


__all__ = [
    "EnginePlugin",
    "PluginRegistry",
    "ScreenshotCapturePlugin",
    "RequestRecorderPlugin",
]
