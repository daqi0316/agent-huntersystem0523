"""
插件注册便利入口
"""

from .base import PluginRegistry, ScreenshotCapturePlugin, RequestRecorderPlugin

# 默认注册内置插件
_registered = False


def register_default_plugins():
    """注册所有内置插件"""
    global _registered
    if _registered:
        return

    PluginRegistry.register(ScreenshotCapturePlugin())
    PluginRegistry.register(RequestRecorderPlugin())
    _registered = True

    from .. import structlog
    logger = structlog.get_logger()
    logger.info("默认插件已注册")


__all__ = ["register_default_plugins"]
