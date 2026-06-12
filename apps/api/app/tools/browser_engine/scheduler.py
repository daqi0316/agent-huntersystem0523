"""
引擎调度器 — 定时/事件触发爬取

复用 main.py 已有的 ``asyncio.create_task`` 模式，不引入 APScheduler。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from .manager.engine_manager import EngineManager
from .monitoring.metrics import monitored_fetch

logger = logging.getLogger(__name__)

# 默认爬取间隔（秒）
DEFAULT_CRAWL_INTERVAL_SECONDS = 3600


# ===== 爬取任务类型 =====

CrawlTask = Callable[[], Coroutine[Any, Any, None]]


async def crawl_platform(
    platform_name: str,
    url: str,
    engine_manager: EngineManager | None = None,
    wait_for: str | None = None,
    timeout: int = 30000,
) -> None:
    """
    执行单个平台的爬取任务 — 带监控

    Args:
        platform_name: 平台标识（boss_zhipin, liepin, maimai ...）
        url: 目标 URL
        engine_manager: 引擎管理器，None 则创建默认实例
        wait_for: 等待的 CSS 选择器
        timeout: 超时（毫秒）
    """
    mgr = engine_manager or EngineManager()
    logger.info("调度爬取", platform=platform_name, url=url)

    result = await monitored_fetch(
        engine_manager=mgr,
        url=url,
        platform_name=platform_name,
        timeout=timeout,
    )

    if result.success:
        logger.info("爬取成功", platform=platform_name, url=url, engine=result.engine_used)
    else:
        logger.warning(
            "爬取失败",
            platform=platform_name,
            url=url,
            error=result.error_message,
            engine=result.engine_used,
        )


# ===== 定时调度循环 =====

async def platform_crawl_loop(
    platform_name: str,
    url: str,
    interval_seconds: int = DEFAULT_CRAWL_INTERVAL_SECONDS,
    wait_for: str | None = None,
    timeout: int = 30000,
) -> None:
    """
    平台爬取定时循环 — 由 lifespan create_task 启动

    用法 (main.py):
        task = asyncio.create_task(platform_crawl_loop(
            "boss_zhipin", "https://www.zhipin.com/web/geek/job",
            interval_seconds=3600,
        ))
    """
    mgr = EngineManager()
    logger.info(
        "爬取循环启动",
        platform=platform_name,
        url=url,
        interval=f"{interval_seconds}s",
    )

    while True:
        try:
            await crawl_platform(
                platform_name=platform_name,
                url=url,
                engine_manager=mgr,
                wait_for=wait_for,
                timeout=timeout,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("爬取循环异常", platform=platform_name, error=str(e))

        await asyncio.sleep(interval_seconds)


# ===== 按需执行 =====

async def run_crawl_task(
    platform_name: str,
    url: str,
    wait_for: str | None = None,
    timeout: int = 30000,
) -> dict:
    """
    按需执行一次爬取任务（API 端点调用）

    Returns:
        包含结果信息的 dict
    """
    mgr = EngineManager()
    result = await monitored_fetch(
        engine_manager=mgr,
        url=url,
        platform_name=platform_name,
        timeout=timeout,
    )

    return {
        "success": result.success,
        "engine_used": result.engine_used.value if result.engine_used else None,
        "url": result.url or url,
        "title": result.title,
        "html_length": len(result.html) if result.html else 0,
        "error": result.error_message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "crawl_platform",
    "platform_crawl_loop",
    "run_crawl_task",
]
