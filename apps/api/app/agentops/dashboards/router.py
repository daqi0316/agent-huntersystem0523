"""AgentOps 看板 API 路由 (P2-C Stage 14).

提供 DashboardMetrics 的 REST 接口，供前端 Debug Console / 质量看板 / 成本看板消费。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.agentops.dashboards.metrics import DashboardMetrics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard/agentops", tags=["AgentOps Dashboard"])


@router.get("/overview")
async def get_overview():
    """系统概览统计。"""
    return await DashboardMetrics.overview()


@router.get("/quality")
async def get_quality():
    """质量汇总。"""
    return await DashboardMetrics.quality_summary()


@router.get("/recent-runs")
async def get_recent_runs(limit: int = 20):
    """最近实验运行记录。"""
    return await DashboardMetrics.recent_runs(limit=limit)


@router.get("/evaluators")
async def get_evaluator_performance():
    """各评估器的性能统计。"""
    return await DashboardMetrics.evaluator_performance()


@router.get("/feedback")
async def get_feedback_summary():
    """反馈汇总。"""
    return await DashboardMetrics.feedback_summary()


# Phase C: Trace + 成本时间趋势


@router.get("/traces/{trace_id}")
async def get_trace_detail(trace_id: str):
    """Trace 事件链详情（瀑布图数据）。"""
    result = await DashboardMetrics.trace_detail(trace_id)
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Trace not found")
    return result


@router.get("/events")
async def search_events(
    event_type: str = "", entity_type: str = "", entity_id: str = "",
    limit: int = 50,
):
    """搜索业务事件。"""
    return await DashboardMetrics.trace_search(
        event_type=event_type, entity_type=entity_type,
        entity_id=entity_id, limit=limit,
    )



