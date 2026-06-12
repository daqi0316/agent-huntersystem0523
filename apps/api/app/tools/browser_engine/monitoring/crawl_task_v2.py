"""
带引擎降级监控的采集任务
核心降级检测逻辑不变（原文 Celery → arq 适配）
"""

from __future__ import annotations

from typing import Optional
import structlog

logger = structlog.get_logger()


async def crawl_with_engine_monitoring(
    platform_name: str,
    keyword: str,
    task_id: str,
    search_url: str,
) -> dict:
    """
    增强版采集任务 — 记录引擎降级事件
    对应原文 @shared_task(bind=True, max_retries=3)
    """
    from ..manager.engine_manager import EngineManager

    engine_manager = EngineManager()

    # 执行采集（自动降级）
    result = await engine_manager.fetch_with_fallback(
        url=search_url,
        platform_name=platform_name,
    )

    # 记录引擎使用情况
    logger.info(
        "采集任务完成",
        task_id=task_id,
        platform=platform_name,
        engine_used=result.engine_used,
        success=result.success,
    )

    # 如果发生降级，发送告警
    preferred_engine = engine_manager.get_preferred_engine(platform_name)
    if result.engine_used and result.engine_used.value != preferred_engine.value:
        logger.warning(
            "引擎降级发生",
            task_id=task_id,
            platform=platform_name,
            preferred=preferred_engine.value,
            actual=result.engine_used.value,
            url=search_url,
        )

    return {
        "platform": platform_name,
        "engine_used": result.engine_used.value if result.engine_used else None,
        "success": result.success,
        "html_length": len(result.html) if result.html else 0,
    }


__all__ = ["crawl_with_engine_monitoring"]
