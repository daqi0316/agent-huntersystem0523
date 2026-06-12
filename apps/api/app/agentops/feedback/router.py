"""Feedback API — P2-C Stage 11 用户反馈入口。

路由前缀: /api/v1/feedback

端点:
  POST   /feedback          — 提交反馈（最终用户 / 标注员）
  POST   /feedback/batch    — 批量提交反馈
  GET    /feedback          — 查询反馈列表
  GET    /feedback/{id}     — 查询单条反馈
  GET    /feedback/stats    — 聚合统计

鉴权: 所有端点需有效 JWT（Depends(get_current_user_id)）
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.agentops.feedback.schemas import (
    FeedbackCategory,
    FeedbackCreate,
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackSource,
    FeedbackStats,
    FeedbackTarget,
)
from app.agentops.feedback.service import FeedbackService
from app.core.database import AsyncSession, get_db
from app.core.dependencies import get_current_user_id
from app.core.response import error, ok_list, success

logger = logging.getLogger(__name__)

router = APIRouter()


class BatchFeedbackItem(BaseModel):
    """单条批量反馈条目。"""

    category: FeedbackCategory
    score: float = Field(..., ge=0.0, le=1.0)
    reason: str | None = Field(None, max_length=2000)
    target: FeedbackTarget = Field(default_factory=FeedbackTarget)
    source: FeedbackSource = Field(default=FeedbackSource.END_USER)
    tags: list[str] = Field(default_factory=list, max_length=10)


class BatchFeedbackRequest(BaseModel):
    """批量反馈请求。"""

    items: list[BatchFeedbackItem] = Field(..., max_length=50, description="反馈条目（最多 50 条）")


@router.post("", response_model=dict)
async def submit_feedback(
    req: FeedbackCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """提交一条用户反馈。

    反馈自动关联当前 AgentOps 执行链路（trace_id / span_id），
    并写入 Langfuse Score（针对 relevance / accuracy / completeness / quality 类别）。
    """
    service = FeedbackService(db=db)
    model = await service.create_feedback(req, user_id=user_id)
    if model is None:
        return error("反馈提交失败", status_code=500)
    return success(model.to_response().model_dump())


@router.post("/batch", response_model=dict)
async def submit_feedback_batch(
    req: BatchFeedbackRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """批量提交反馈（最多 50 条）。"""
    service = FeedbackService(db=db)
    accepted = 0
    errors: list[str] = []
    for item in req.items:
        create_req = FeedbackCreate(
            category=item.category,
            score=item.score,
            reason=item.reason,
            target=item.target,
            source=item.source,
            tags=item.tags,
        )
        model = await service.create_feedback(create_req, user_id=user_id)
        if model is not None:
            accepted += 1
        else:
            errors.append(f"category={item.category.value} 提交失败")

    return {
        "success": True,
        "data": {"accepted": accepted, "errors": errors},
    }


@router.get("", response_model=dict)
async def list_feedback(
    category: str | None = Query(None, description="按类别筛选"),
    source: str | None = Query(None, description="按来源筛选"),
    trace_id: str | None = Query(None, description="按 trace ID 筛选"),
    user_id: str | None = Query(None, description="按用户 ID 筛选"),
    session_id: str | None = Query(None, description="按 session ID 筛选"),
    entity_type: str | None = Query(None, description="按实体类型筛选"),
    entity_id: str | None = Query(None, description="按实体 ID 筛选"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """查询反馈列表（按创建时间倒序）。"""
    service = FeedbackService(db=db)
    items, total = await service.list_feedback(
        category=category,
        source=source,
        trace_id=trace_id,
        user_id=user_id,
        session_id=session_id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=skip,
    )
    return ok_list(
        items=[m.to_response().model_dump() for m in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/stats", response_model=dict)
async def feedback_stats(
    trace_id: str | None = Query(None, description="按 trace ID 聚合"),
    user_id: str | None = Query(None, description="按用户 ID 聚合"),
    session_id: str | None = Query(None, description="按 session ID 聚合"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """反馈聚合统计 — 按 category 计算平均分和条数。"""
    service = FeedbackService(db=db)
    stats = await service.get_stats(
        trace_id=trace_id,
        user_id=user_id,
        session_id=session_id,
    )
    return success(stats.model_dump())


@router.get("/{feedback_id}", response_model=dict)
async def get_feedback(
    feedback_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """查询单条反馈详情。"""
    service = FeedbackService(db=db)
    model = await service.get_feedback(feedback_id)
    if model is None:
        return error("反馈不存在", status_code=404)
    return success(model.to_response().model_dump())
