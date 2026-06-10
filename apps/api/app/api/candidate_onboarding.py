"""P1-C: 入职后跟踪 API — OnboardingTracking / OnboardingCheckpoint / ProbationFeedback。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, func

from app.core.org_context import org_scoped_db
from app.core.response import error, success
from app.models.candidate_onboarding import (
    OnboardingTracking,
    OnboardingCheckpoint,
    ProbationFeedback,
    CheckpointStatus,
    CheckpointType,
)
from app.models.candidate_timeline import CandidateFollowupTask, CandidateFollowupPriority
from app.schemas.candidate_onboarding import (
    OnboardingTrackingCreate,
    OnboardingTrackingUpdate,
    OnboardingCheckpointCreate,
    OnboardingCheckpointUpdate,
    ProbationFeedbackCreate,
    ProbationFeedbackUpdate,
)

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


# ── helpers ──

def _tracking_to_dict(item: OnboardingTracking) -> dict[str, Any]:
    return {
        "id": item.id,
        "candidate_id": item.candidate_id,
        "application_id": item.application_id,
        "offer_id": item.offer_id,
        "hire_date": item.hire_date,
        "department": item.department,
        "manager_id": item.manager_id,
        "mentor_id": item.mentor_id,
        "status": _enum_value(item.status),
        "risk_level": _enum_value(item.risk_level),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _checkpoint_to_dict(item: OnboardingCheckpoint) -> dict[str, Any]:
    return {
        "id": item.id,
        "onboarding_id": item.onboarding_id,
        "checkpoint_type": _enum_value(item.checkpoint_type),
        "due_at": item.due_at,
        "completed_at": item.completed_at,
        "status": _enum_value(item.status),
        "owner_id": item.owner_id,
        "summary": item.summary,
        "risk_flags": item.risk_flags or [],
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _feedback_to_dict(item: ProbationFeedback) -> dict[str, Any]:
    return {
        "id": item.id,
        "onboarding_id": item.onboarding_id,
        "checkpoint_id": item.checkpoint_id,
        "reviewer_id": item.reviewer_id,
        "performance_score": item.performance_score,
        "culture_fit_score": item.culture_fit_score,
        "ramp_up_score": item.ramp_up_score,
        "communication_score": item.communication_score,
        "retention_risk": item.retention_risk,
        "feedback_text": item.feedback_text,
        "pass_probation": item.pass_probation,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


async def _ensure_checkpoints(db, tracking: OnboardingTracking) -> list[OnboardingCheckpoint]:
    """offer accepted / status=preboarding 时自动生成 day_1 ~ month_6 检查点 + 入职前提醒任务。"""
    existing = (await db.execute(
        select(OnboardingCheckpoint).where(OnboardingCheckpoint.onboarding_id == tracking.id)
    )).scalars().all()
    if existing:
        # 入职提醒 followup task 可能已存在，不再重复生成
        return list(existing)

    now = _now_utc()
    hire = tracking.hire_date
    checkpoints: list[OnboardingCheckpoint] = []

    # day_1 入职当天
    checkpoints.append(OnboardingCheckpoint(
        onboarding_id=tracking.id,
        checkpoint_type=CheckpointType.DAY_1,
        due_at=now if not hire else datetime(hire.year, hire.month, hire.day, tzinfo=timezone.utc),
        status=CheckpointStatus.PENDING,
    ))

    if hire:
        for offset_days, ctype in [
            (7, CheckpointType.DAY_7),
            (30, CheckpointType.MONTH_1),
            (90, CheckpointType.MONTH_3),
            (180, CheckpointType.MONTH_6),
        ]:
            due = datetime(hire.year, hire.month, hire.day, tzinfo=timezone.utc) + timedelta(days=offset_days)
            checkpoints.append(OnboardingCheckpoint(
                onboarding_id=tracking.id,
                checkpoint_type=ctype,
                due_at=due,
                status=CheckpointStatus.PENDING,
            ))

    for cp in checkpoints:
        db.add(cp)

    # 入职前提醒 followup tasks（不重复创建）
    existing_tasks = (await db.execute(
        select(CandidateFollowupTask).where(
            CandidateFollowupTask.candidate_id == tracking.candidate_id,
            CandidateFollowupTask.auto_generated.is_(True),
            CandidateFollowupTask.trigger_rule.in_(["preboarding_7d", "preboarding_1d"]),
        )
    )).scalars().all()
    existing_rules = {t.trigger_rule for t in existing_tasks}

    followups: list[CandidateFollowupTask] = []
    if hire:
        hire_dt = datetime(hire.year, hire.month, hire.day, tzinfo=timezone.utc)
        # 入职前 7 天：确认材料和意愿
        if "preboarding_7d" not in existing_rules:
            pre_7 = hire_dt - timedelta(days=7)
            followups.append(CandidateFollowupTask(
                candidate_id=tracking.candidate_id,
                due_at=pre_7,
                task_type="preboarding_check",
                title="入职前 7 天，确认候选人材料和入职意愿",
                priority=CandidateFollowupPriority.HIGH,
                auto_generated=True,
                trigger_rule="preboarding_7d",
            ))
        # 入职前 1 天：确认到岗
        if "preboarding_1d" not in existing_rules:
            pre_1 = hire_dt - timedelta(days=1)
            followups.append(CandidateFollowupTask(
                candidate_id=tracking.candidate_id,
                due_at=pre_1,
                task_type="preboarding_check",
                title="入职前 1 天，确认候选人到岗",
                priority=CandidateFollowupPriority.URGENT,
                auto_generated=True,
                trigger_rule="preboarding_1d",
            ))

    for task in followups:
        db.add(task)

    await db.commit()
    for cp in checkpoints:
        await db.refresh(cp)
    return checkpoints


# ── onboarding trackings ──

@router.post("/onboarding-trackings", status_code=201)
async def create_tracking(data: OnboardingTrackingCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    item = OnboardingTracking(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    # auto-generate checkpoints on creation
    await _ensure_checkpoints(db, item)
    return success(_tracking_to_dict(item))


@router.get("/onboarding-trackings")
async def list_trackings(status: str | None = None, candidate_id: str | None = None, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    stmt = select(OnboardingTracking).order_by(OnboardingTracking.created_at.desc())
    if status:
        stmt = stmt.where(OnboardingTracking.status == status)
    if candidate_id:
        stmt = stmt.where(OnboardingTracking.candidate_id == candidate_id)
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return success({"items": [_tracking_to_dict(item) for item in items], "total": len(items)})


@router.get("/onboarding-trackings/{tracking_id}")
async def get_tracking(tracking_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    result = await db.execute(
        select(OnboardingTracking).where(OnboardingTracking.id == tracking_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return error("入职跟踪记录不存在", status_code=404)
    # load checkpoints
    cp_result = await db.execute(
        select(OnboardingCheckpoint).where(OnboardingCheckpoint.onboarding_id == tracking_id).order_by(OnboardingCheckpoint.due_at)
    )
    checkpoints = [{"checkpoint": _checkpoint_to_dict(cp)} for cp in cp_result.scalars().all()]
    # load feedbacks
    fb_result = await db.execute(
        select(ProbationFeedback).where(ProbationFeedback.onboarding_id == tracking_id).order_by(ProbationFeedback.created_at.desc())
    )
    feedbacks = [_feedback_to_dict(fb) for fb in fb_result.scalars().all()]
    return success({
        **_tracking_to_dict(item),
        "checkpoints": checkpoints,
        "feedbacks": feedbacks,
    })


@router.patch("/onboarding-trackings/{tracking_id}")
async def update_tracking(tracking_id: str, data: OnboardingTrackingUpdate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    result = await db.execute(select(OnboardingTracking).where(OnboardingTracking.id == tracking_id))
    item = result.scalar_one_or_none()
    if not item:
        return error("入职跟踪记录不存在", status_code=404)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    # if status was updated to preboarding/onboarded, ensure checkpoints
    if data.status in ("preboarding", "onboarded"):
        await _ensure_checkpoints(db, item)
    return success(_tracking_to_dict(item))


# ── checkpoints ──

@router.get("/onboarding-trackings/{tracking_id}/checkpoints")
async def list_checkpoints(tracking_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    result = await db.execute(
        select(OnboardingCheckpoint).where(OnboardingCheckpoint.onboarding_id == tracking_id).order_by(OnboardingCheckpoint.due_at)
    )
    items = list(result.scalars().all())
    return success({"items": [_checkpoint_to_dict(item) for item in items], "total": len(items)})


@router.post("/onboarding-checkpoints", status_code=201)
async def create_checkpoint(data: OnboardingCheckpointCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    item = OnboardingCheckpoint(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return success(_checkpoint_to_dict(item))


@router.patch("/onboarding-checkpoints/{checkpoint_id}")
async def update_checkpoint(checkpoint_id: str, data: OnboardingCheckpointUpdate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    result = await db.execute(select(OnboardingCheckpoint).where(OnboardingCheckpoint.id == checkpoint_id))
    item = result.scalar_one_or_none()
    if not item:
        return error("检查点不存在", status_code=404)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return success(_checkpoint_to_dict(item))


# ── probation feedbacks ──

@router.post("/probation-feedbacks", status_code=201)
async def create_feedback(data: ProbationFeedbackCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    item = ProbationFeedback(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return success(_feedback_to_dict(item))


@router.patch("/probation-feedbacks/{feedback_id}")
async def update_feedback(feedback_id: str, data: ProbationFeedbackUpdate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    result = await db.execute(select(ProbationFeedback).where(ProbationFeedback.id == feedback_id))
    item = result.scalar_one_or_none()
    if not item:
        return error("试用期反馈不存在", status_code=404)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return success(_feedback_to_dict(item))


@router.get("/onboarding-trackings/{tracking_id}/feedbacks")
async def list_feedbacks(tracking_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    result = await db.execute(
        select(ProbationFeedback).where(ProbationFeedback.onboarding_id == tracking_id).order_by(ProbationFeedback.created_at.desc())
    )
    items = list(result.scalars().all())
    return success({"items": [_feedback_to_dict(item) for item in items], "total": len(items)})


# ── analytics ──

@router.get("/onboarding-analytics/probation-pass-rate")
async def probation_pass_rate(od=ORG_SCOPED_DEP):
    org_ctx, db = od
    total = (await db.execute(func.count(ProbationFeedback.id).select())).scalar() or 0
    passed = (
        await db.execute(
            select(func.count(ProbationFeedback.id)).where(ProbationFeedback.pass_probation.is_(True))
        )
    ).scalar() or 0
    rate = round(passed / total * 100, 1) if total else 0.0
    return success({
        "total_feedbacks": total,
        "passed": passed,
        "pass_rate": rate,
    })
