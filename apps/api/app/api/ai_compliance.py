"""P5-10: AI 监管合规 API — 申诉 + 人工覆盖。"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.core.response import success
from app.models.appeal import APPEAL_SLA_DAYS, Appeal, AppealStatus
from app.models.audit_log import AuditLogAction
from app.models.recommendation import Recommendation

router = APIRouter()


class CreateAppealRequest(BaseModel):
    target_type: str = Field(..., description="recommendation | interview_evaluation")
    target_id: str
    reason: str = Field(..., min_length=10, max_length=2000)


class ResolveAppealRequest(BaseModel):
    resolution: str = Field(..., min_length=10, max_length=2000)
    accept: bool = Field(..., description="True=支持申诉, False=驳回")


class OverrideRecommendationRequest(BaseModel):
    new_score: int = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=5, max_length=1000)


def _serialize_appeal(a: Appeal) -> dict:
    now = datetime.now(timezone.utc)
    days_left = max(0, (a.due_at - now).days) if a.due_at else None
    return {
        "id": a.id,
        "target_type": a.target_type,
        "target_id": a.target_id,
        "status": a.status.value,
        "reason": a.reason,
        "resolution": a.resolution,
        "resolved_by": a.resolved_by,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "due_at": a.due_at.isoformat() if a.due_at else None,
        "sla_days_left": days_left,
        "overdue": a.due_at < now if a.due_at else False,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/appeals", status_code=201)
async def create_appeal(
    body: CreateAppealRequest,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx

    if body.target_type not in ("recommendation", "interview_evaluation"):
        raise HTTPException(400, "target_type must be 'recommendation' or 'interview_evaluation'")

    target_table = "recommendations" if body.target_type == "recommendation" else "interview_evaluations"
    from sqlalchemy import text as sql_text
    result = await db.execute(
        sql_text(f"SELECT id FROM {target_table} WHERE id = :id AND org_id = :org_id"),
        {"id": body.target_id, "org_id": org_ctx.org_id},
    )
    if result.first() is None:
        raise HTTPException(404, f"{body.target_type} not found in this org")

    existing = (await db.execute(
        select(Appeal).where(
            Appeal.user_id == org_ctx.user_id,
            Appeal.target_id == body.target_id,
            Appeal.status.in_([AppealStatus.PENDING, AppealStatus.IN_REVIEW]),
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "已有未完成的申诉")

    now = datetime.now(timezone.utc)
    appeal = Appeal(
        id=secrets.token_urlsafe(16),
        org_id=org_ctx.org_id,
        user_id=org_ctx.user_id,
        target_type=body.target_type,
        target_id=body.target_id,
        status=AppealStatus.PENDING,
        reason=body.reason,
        due_at=now + timedelta(days=APPEAL_SLA_DAYS),
    )
    db.add(appeal)
    await db.commit()
    await db.refresh(appeal)

    from app.api.audit_logs import log_audit
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.APPEAL_FILED,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={"appeal_id": appeal.id, "target_type": body.target_type, "target_id": body.target_id},
    )
    await db.commit()
    return success(_serialize_appeal(appeal))


@router.get("/appeals")
async def list_appeals(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    q = select(Appeal).where(Appeal.org_id == org_ctx.org_id)
    if status_filter:
        try:
            q = q.where(Appeal.status == AppealStatus(status_filter))
        except ValueError:
            raise HTTPException(400, f"invalid status: {status_filter}")
    q = q.order_by(Appeal.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return success([_serialize_appeal(r) for r in rows])


@router.get("/appeals/{appeal_id}")
async def get_appeal(
    appeal_id: str,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    appeal = (await db.execute(
        select(Appeal).where(Appeal.id == appeal_id, Appeal.org_id == org_ctx.org_id)
    )).scalar_one_or_none()
    if appeal is None:
        raise HTTPException(404, "appeal not found")
    return success(_serialize_appeal(appeal))


@router.post("/appeals/{appeal_id}/resolve")
async def resolve_appeal(
    appeal_id: str,
    body: ResolveAppealRequest,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    org_ctx, db = ctx
    appeal = (await db.execute(
        select(Appeal).where(Appeal.id == appeal_id, Appeal.org_id == org_ctx.org_id)
    )).scalar_one_or_none()
    if appeal is None:
        raise HTTPException(404, "appeal not found")
    if appeal.status not in (AppealStatus.PENDING, AppealStatus.IN_REVIEW):
        raise HTTPException(400, f"appeal in {appeal.status.value}, cannot resolve")

    appeal.status = AppealStatus.RESOLVED_ACCEPTED if body.accept else AppealStatus.RESOLVED_REJECTED
    appeal.resolution = body.resolution
    appeal.resolved_by = org_ctx.user_id
    appeal.resolved_at = datetime.now(timezone.utc)

    from app.api.audit_logs import log_audit
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.APPEAL_RESOLVED,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={
            "appeal_id": appeal.id,
            "target_type": appeal.target_type,
            "target_id": appeal.target_id,
            "accept": body.accept,
        },
    )
    await db.commit()
    return success(_serialize_appeal(appeal))


@router.post("/recommendations/{recommendation_id}/override-score")
async def override_recommendation_score(
    recommendation_id: str,
    body: OverrideRecommendationRequest,
    request: Request,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """人工覆盖 AI 评分 (HR 改分, 落 audit, 设 score_overridden=True)。"""
    org_ctx, db = ctx
    reco = (await db.execute(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.user_id == org_ctx.user_id,
        )
    )).scalar_one_or_none()
    if reco is None:
        raise HTTPException(404, "recommendation not found")

    if reco.score is None:
        raise HTTPException(400, "recommendation has no AI score to override")

    original_score = reco.score
    reco.score = body.new_score
    reco.score_overridden = True
    reco.score_overridden_by = org_ctx.user_id
    reco.score_overridden_at = datetime.now(timezone.utc)
    reco.score_override_reason = body.reason

    from app.api.audit_logs import log_audit
    await log_audit(
        db, org_id=org_ctx.org_id,
        action=AuditLogAction.AI_OVERRIDE,
        actor_user_id=org_ctx.user_id,
        request=request,
        metadata={
            "target_type": "recommendation",
            "target_id": recommendation_id,
            "original_score": original_score,
            "new_score": body.new_score,
            "reason": body.reason,
            "ai_source": reco.ai_score_source,
        },
    )
    await db.commit()
    return success({
        "id": reco.id,
        "score": reco.score,
        "score_overridden": reco.score_overridden,
        "score_overridden_at": reco.score_overridden_at.isoformat(),
        "original_ai_score": original_score,
        "ai_source": reco.ai_score_source,
    })


@router.get("/recommendations/{recommendation_id}/ai-source")
async def get_recommendation_ai_source(
    recommendation_id: str,
    ctx: tuple[OrgContext, AsyncSession] = Depends(org_scoped_db),
):
    """查 AI 评分来源 (前端 hover 显示)。"""
    org_ctx, db = ctx
    reco = (await db.execute(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.user_id == org_ctx.user_id,
        )
    )).scalar_one_or_none()
    if reco is None:
        raise HTTPException(404, "recommendation not found")

    return success({
        "id": reco.id,
        "score": reco.score,
        "score_overridden": reco.score_overridden,
        "ai_source": reco.ai_score_source,
    })
