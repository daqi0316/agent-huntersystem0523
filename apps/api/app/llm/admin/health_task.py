"""LLM Provider 健康检查后台任务。

每 60s 遍历所有 active provider，调 check_connection()。
连续失败 3 次 → 标记 is_active=False，写告警日志。

在 FastAPI lifespan 中启动：
    asyncio.create_task(llm_health_check_loop())
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# 连续失败阈值
_MAX_FAILURES = 3
# 检查间隔（秒）
_CHECK_INTERVAL = 60


class HealthChecker:
    """健康检查器 — 追踪每个 provider 的连续失败次数。"""

    def __init__(self):
        self._failure_counts: dict[str, int] = {}

    async def run_loop(self):
        """后台循环，每分钟检查一次。"""
        logger.info("LLM 健康检查后台任务已启动（间隔=%ds, 最大失败=%d）", _CHECK_INTERVAL, _MAX_FAILURES)
        while True:
            try:
                await self._check_all()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("LLM 健康检查异常: %s", e)
            await asyncio.sleep(_CHECK_INTERVAL)

    async def _check_all(self):
        """遍历所有 active provider 检查连通性。"""
        try:
            from app.llm.models.llm_provider import LlmProvider
            from app.llm.router import get_model_router
            from app.llm.admin.crypto import decrypt_api_key

            router = get_model_router()

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(LlmProvider).where(LlmProvider.is_active == True)
                )
                providers = result.scalars().all()

                for provider in providers:
                    api_key = decrypt_api_key(provider.api_key_enc) if provider.api_key_enc else None

                    try:
                        health = await router.check_connection(
                            provider_type=provider.provider_type,
                            model_name=provider.model_name,
                            api_key=api_key,
                            base_url=provider.base_url,
                        )
                    except Exception as e:
                        health = {"success": False, "error": str(e)}

                    if health.get("success"):
                        # 恢复
                        if provider.id in self._failure_counts:
                            old_count = self._failure_counts.pop(provider.id, 0)
                            if old_count >= _MAX_FAILURES:
                                logger.info("LLM 模型 %s 已恢复（连续失败清零）", provider.name)
                    else:
                        # 失败计数
                        count = self._failure_counts.get(provider.id, 0) + 1
                        self._failure_counts[provider.id] = count
                        logger.warning(
                            "LLM 模型 %s 健康检查失败 (%d/%d): %s",
                            provider.name, count, _MAX_FAILURES, health.get("error"),
                        )

                        if count >= _MAX_FAILURES:
                            logger.error(
                                "LLM 模型 %s 连续失败 %d 次，标记为 inactive",
                                provider.name, _MAX_FAILURES,
                            )
                            await db.execute(
                                update(LlmProvider)
                                .where(LlmProvider.id == provider.id)
                                .values(is_active=False)
                            )
                            await db.commit()
                            # 清空该 provider 的失败计数
                            self._failure_counts.pop(provider.id, None)

                # 清理已经不 active 的 provider 的失败计数
                active_ids = {p.id for p in providers}
                for pid in list(self._failure_counts.keys()):
                    if pid not in active_ids:
                        self._failure_counts.pop(pid, None)

        except Exception as e:
            logger.error("LLM 健康检查循环异常: %s", e)


# ── 全局单例 ──

_health_checker: HealthChecker | None = None
_health_task: asyncio.Task | None = None


def start_health_check() -> asyncio.Task:
    """启动健康检查后台任务。返回 asyncio.Task。"""
    global _health_checker, _health_task
    if _health_task is not None and not _health_task.done():
        logger.warning("健康检查任务已在运行")
        return _health_task

    _health_checker = HealthChecker()
    _health_task = asyncio.create_task(_health_checker.run_loop())
    return _health_task


def stop_health_check():
    """停止健康检查后台任务。"""
    global _health_task
    if _health_task is not None:
        _health_task.cancel()
        _health_task = None
        logger.info("LLM 健康检查任务已停止")
