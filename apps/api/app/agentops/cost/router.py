"""Cost API 路由 — 提供成本看板数据接口。

挂载到 /dashboard/agentops/cost/* 下。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.agentops.cost.service import CostService
from app.agentops.cost.pricing import get_known_models

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard/agentops/cost", tags=["AgentOps Cost"])


@router.get("/summary")
async def get_cost_summary(days: int = Query(30, description="统计天数")):
    """成本概览卡片数据。"""
    return await CostService.summary(days=days)


@router.get("/timeseries")
async def get_cost_timeseries(days: int = Query(30, description="聚合天数")):
    """成本时间趋势（按天聚合）。"""
    return await CostService.timeseries(days=days)


@router.get("/by-model")
async def get_cost_by_model(days: int = Query(30, description="统计天数")):
    """按模型分解成本。"""
    return await CostService.by_model(days=days)


@router.get("/by-user")
async def get_cost_by_user(
    days: int = Query(30, description="统计天数"),
    limit: int = Query(20, description="返回用户数上限"),
):
    """按用户分解成本。"""
    return await CostService.by_user(days=days, limit=limit)


@router.get("/model-pricing")
async def get_model_pricing():
    """已知模型定价表。"""
    return {"models": get_known_models()}
