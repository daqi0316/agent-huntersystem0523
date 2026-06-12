"""
FastAPI 集成 — 引擎生命周期挂载 + 健康端点 + 告警通知
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from .manager.engine_manager import EngineManager
from .manager.lifecycle import EngineLifecycleManager
from .monitoring.health import get_engine_health
from .monitoring.alert_webhook import AlertWebhook
from . import EngineType, EngineStatus

logger = logging.getLogger(__name__)


ENGINE_HEALTH_CHECK_INTERVAL = 60


@asynccontextmanager
async def engine_lifespan() -> AsyncIterator[None]:
    """
    FastAPI lifespan 集成 — 在 startup 启动引擎，shutdown 关闭。

    用法 --- 在 ``main.py`` 的 ``lifespan`` 内:
        async with engine_lifespan():
            yield
    """
    lifecycle = EngineLifecycleManager()
    webhook_url: str | None = None  # TODO: 从 settings 读取

    try:
        await lifecycle.startup()
        await lifecycle.health_check_loop(interval=ENGINE_HEALTH_CHECK_INTERVAL)

        if webhook_url:
            _wire_alert(lifecycle, webhook_url)

        logger.info("browser_engine 已就绪")
    except Exception as e:
        logger.warning("browser_engine 启动失败（非致命）: %s", e)

    yield

    try:
        await lifecycle.shutdown()
        logger.info("browser_engine 已关闭")
    except Exception as e:
        logger.warning("browser_engine 关闭异常: %s", e)


def _wire_alert(lifecycle: EngineLifecycleManager, webhook_url: str) -> None:
    """将告警接入引擎生命周期"""
    alert = AlertWebhook(webhook_url=webhook_url, channel="feishu")
    original = lifecycle._run_health_loop

    async def alerting_loop(interval: int) -> None:
        while True:
            try:
                results = await lifecycle._manager.health_check_all()
                unavailable = {
                    et: st
                    for et, st in results.items()
                    if st != EngineStatus.AVAILABLE
                }
                if unavailable:
                    alert.send_health_summary(results)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("健康检查+告警异常: %s", e)
            await asyncio.sleep(interval)

    lifecycle._run_health_loop = alerting_loop  # type: ignore[method-assign]
    logger.info("告警 webhook 已接入")


async def browser_engines_health() -> dict:
    """
    FastAPI 健康检查端点 — 返回引擎状态

    在 router 中注册:
        @router.get("/health/browser-engines")
        async def _():
            return await browser_engines_health()
    """
    try:
        result = await get_engine_health()
        return {"status": "ok", "engines": result}
    except Exception as e:
        return {"status": "degraded", "error": str(e), "engines": {}}


def register_engine_routes(router):
    """
    在 API router 上注册引擎相关端点

    用法:
        from fastapi import APIRouter
        r = APIRouter()
        register_engine_routes(r)
    """
    from fastapi import APIRouter

    if not isinstance(router, APIRouter):
        router = APIRouter()

    @router.get("/health/browser-engines")
    async def health_browser_engines():
        return await browser_engines_health()

    return router


__all__ = [
    "engine_lifespan",
    "browser_engines_health",
    "register_engine_routes",
]
