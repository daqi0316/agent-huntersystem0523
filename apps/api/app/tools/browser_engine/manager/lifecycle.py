"""
引擎生命周期管理（★ 工程化扩展）
启动预热 + 优雅关闭 + 健康检查循环
"""

import asyncio
from typing import Optional
import structlog

from .. import EngineType
from .engine_manager import EngineManager

logger = structlog.get_logger()


class EngineLifecycleManager:
    """引擎生命周期管理"""

    INIT_ORDER = [
        EngineType.HTTP,
        EngineType.INVISIBLE_PLAYWRIGHT,
        EngineType.BROWSER_USE,
    ]

    def __init__(self):
        self._manager = EngineManager()
        self._health_task: Optional[asyncio.Task] = None

    async def startup(self):
        """应用启动时调用 — 顺序初始化"""
        logger.info("引擎生命周期：开始启动")
        for engine_type in self.INIT_ORDER:
            try:
                engine = self._manager._get_or_create_engine(engine_type)
                await engine.warmup()
                logger.info(f"引擎 {engine_type} 预热完成")
            except Exception as e:
                logger.error(f"引擎 {engine_type} 启动失败", error=str(e))

    async def shutdown(self, grace_period: int = 30):
        """应用关闭时调用 — 优雅关闭"""
        logger.info("引擎生命周期：开始关闭")
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        async with asyncio.timeout(grace_period):
            await self._manager.close_all()

        logger.info("引擎生命周期：关闭完成")

    async def health_check_loop(self, interval: int = 30):
        """定期健康检查循环"""
        logger.info("引擎健康检查循环启动", interval_seconds=interval)
        self._health_task = asyncio.create_task(self._run_health_loop(interval))

    async def _run_health_loop(self, interval: int):
        """内部健康检查循环"""
        while True:
            try:
                results = await self._manager.health_check_all()
                for engine_type, status in results.items():
                    if status != EngineStatus.AVAILABLE:
                        logger.warning(
                            f"引擎 {engine_type} 状态异常",
                            status=status.value,
                        )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("健康检查循环异常", error=str(e))

            await asyncio.sleep(interval)


__all__ = ["EngineLifecycleManager"]
