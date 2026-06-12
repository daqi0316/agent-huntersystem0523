"""CostService — LLM 成本聚合查询引擎。

提供多维度的成本/Token 聚合，供 API 路由和前端使用。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Float, func, select, text

from app.agentops.cost.models import LLMGenerationRecord
from app.agentops.cost.pricing import get_known_models
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class CostService:
    """成本查询服务 — 所有方法都是类方法，方便调用。"""

    # ═══════════════════════════════════════════════════════════
    # Summary（概览卡片数据）
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def summary(cls, days: int = 30) -> dict[str, Any]:
        """获取成本概览。"""
        now = datetime.now(UTC)
        since = now - timedelta(days=days)

        async with AsyncSessionLocal() as db:
            # 总成本 + 总 tokens
            row = (
                await db.execute(
                    select(
                        func.coalesce(func.sum(LLMGenerationRecord.estimated_cost), 0.0).label("total_cost"),
                        func.coalesce(func.sum(LLMGenerationRecord.total_tokens), 0).label("total_tokens"),
                        func.count(LLMGenerationRecord.id).label("total_calls"),
                        func.avg(LLMGenerationRecord.duration_ms).label("avg_duration_ms"),
                    ).where(LLMGenerationRecord.created_at >= since)
                )
            ).one()

            # 今日
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_row = (
                await db.execute(
                    select(
                        func.coalesce(func.sum(LLMGenerationRecord.estimated_cost), 0.0).label("today_cost"),
                        func.coalesce(func.sum(LLMGenerationRecord.total_tokens), 0).label("today_tokens"),
                        func.count(LLMGenerationRecord.id).label("today_calls"),
                    ).where(LLMGenerationRecord.created_at >= today_start)
                )
            ).one()

            # 模型数量
            model_count_row = (
                await db.execute(
                    select(func.count(func.distinct(LLMGenerationRecord.model)))
                    .where(LLMGenerationRecord.created_at >= since)
                )
            ).scalar() or 0

        return {
            "total_cost": round(float(row.total_cost), 6),
            "total_tokens": int(row.total_tokens),
            "total_calls": int(row.total_calls),
            "avg_duration_ms": round(float(row.avg_duration_ms), 2) if row.avg_duration_ms else 0.0,
            "today_cost": round(float(today_row.today_cost), 6),
            "today_tokens": int(today_row.today_tokens),
            "today_calls": int(today_row.today_calls),
            "model_count": int(model_count_row),
            "currency": "USD",
        }

    # ═══════════════════════════════════════════════════════════
    # 时间趋势（按天聚合）
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def timeseries(cls, days: int = 30) -> dict[str, Any]:
        """按天聚合成本 + token 用量。"""
        since = datetime.now(UTC) - timedelta(days=days)
        async with AsyncSessionLocal() as db:
            stmt = text("""
                SELECT
                    DATE(created_at AT TIME ZONE 'UTC') AS day,
                    COUNT(*) AS calls,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(estimated_cost), 0.0) AS cost,
                    COALESCE(AVG(duration_ms), 0.0) AS avg_duration_ms
                FROM agent_llm_generations
                WHERE created_at >= :since
                GROUP BY day
                ORDER BY day ASC
            """).bindparams(since=since)
            result = await db.execute(stmt)
            rows = result.all()

        daily = [
            {
                "date": str(r.day),
                "calls": int(r.calls),
                "total_tokens": int(r.total_tokens),
                "prompt_tokens": int(r.prompt_tokens),
                "completion_tokens": int(r.completion_tokens),
                "cost": round(float(r.cost), 6),
                "avg_duration_ms": round(float(r.avg_duration_ms), 2),
            }
            for r in rows
        ]

        total_cost = sum(d["cost"] for d in daily)
        total_tokens = sum(d["total_tokens"] for d in daily)
        total_calls = sum(d["calls"] for d in daily)

        return {
            "daily": daily,
            "summary": {
                "total_cost": round(total_cost, 6),
                "total_tokens": total_tokens,
                "total_calls": total_calls,
                "currency": "USD",
            },
        }

    # ═══════════════════════════════════════════════════════════
    # 按模型分解
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def by_model(cls, days: int = 30) -> list[dict[str, Any]]:
        """各模型的成本分解。"""
        since = datetime.now(UTC) - timedelta(days=days)
        async with AsyncSessionLocal() as db:
            stmt = text("""
                SELECT
                    model,
                    COUNT(*) AS calls,
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(estimated_cost), 0.0) AS cost,
                    COALESCE(AVG(duration_ms), 0.0) AS avg_duration_ms
                FROM agent_llm_generations
                WHERE created_at >= :since
                GROUP BY model
                ORDER BY cost DESC
            """).bindparams(since=since)
            result = await db.execute(stmt)
            rows = result.all()

        return [
            {
                "model": r.model,
                "calls": int(r.calls),
                "prompt_tokens": int(r.prompt_tokens),
                "completion_tokens": int(r.completion_tokens),
                "total_tokens": int(r.total_tokens),
                "cost": round(float(r.cost), 6),
                "avg_duration_ms": round(float(r.avg_duration_ms), 2),
            }
            for r in rows
        ]

    # ═══════════════════════════════════════════════════════════
    # 按用户分解
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def by_user(cls, days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
        """各用户的成本分解。"""
        since = datetime.now(UTC) - timedelta(days=days)
        async with AsyncSessionLocal() as db:
            stmt = text("""
                SELECT
                    user_id,
                    COUNT(*) AS calls,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(estimated_cost), 0.0) AS cost
                FROM agent_llm_generations
                WHERE created_at >= :since
                  AND user_id != ''
                GROUP BY user_id
                ORDER BY cost DESC
                LIMIT :limit
            """).bindparams(since=since, limit=limit)
            result = await db.execute(stmt)
            rows = result.all()

        return [
            {
                "user_id": r.user_id,
                "calls": int(r.calls),
                "total_tokens": int(r.total_tokens),
                "cost": round(float(r.cost), 6),
            }
            for r in rows
        ]

    # ═══════════════════════════════════════════════════════════
    # 模型定价表（用于前端展示）
    # ═══════════════════════════════════════════════════════════

    @classmethod
    async def model_pricing_list(cls) -> list[dict]:
        """返回已知模型定价列表。"""
        return get_known_models()
