"""候选人 CRUD API + 生命周期时间线。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.org_context import org_scoped_db
from app.core.response import error, success
from app.models.application import Application
from app.models.candidate_state import CandidateStateHistory
from app.models.interview import Interview
from app.models.interview_evaluation import InterviewEvaluation
from app.models.job_position import JobPosition
from app.models.job_profile import JobProfile
from app.models.rejection import CandidateRejectionRecord
from app.schemas.candidate import CandidateCreate, CandidateRead, CandidateUpdate
from app.schemas.candidate_decision_chain import CandidateDecisionChainResponse
from app.schemas.candidate_state import CandidateStateTransitionRequest
from app.schemas.common import ListResponse
from app.services.candidate import CandidateService
from app.services.candidate_state import (
    CandidateStateService,
    CandidateStateTransitionError,
)

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


@router.get("", response_model=ListResponse[CandidateRead])
async def list_candidates(
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    status: str | None = None,
    od=ORG_SCOPED_DEP,
):
    """分页查询候选人列表 (RLS 自动隔离 org)。"""
    org_ctx, db = od
    service = CandidateService(db)
    items, total = await service.list(skip=skip, limit=limit, search=search, status=status)
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{candidate_id}")
async def get_candidate(candidate_id: str, od=ORG_SCOPED_DEP):
    """获取候选人详情 (RLS 自动隔离)。"""
    org_ctx, db = od
    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)
    return success(candidate)


@router.get("/{candidate_id}/decision-chain", response_model=CandidateDecisionChainResponse)
async def candidate_decision_chain(candidate_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)

    history_result = await db.execute(
        select(CandidateStateHistory)
        .where(CandidateStateHistory.candidate_id == candidate_id)
        .order_by(CandidateStateHistory.created_at.asc())
    )
    state_history = list(history_result.scalars().all())

    app_result = await db.execute(select(Application).where(Application.candidate_id == candidate_id))
    applications = list(app_result.scalars().all())

    job_ids = [app.job_id for app in applications if app.job_id]
    if job_ids:
        job_result = await db.execute(select(JobPosition).where(JobPosition.id.in_(job_ids)))
        jobs_by_id = {job.id: job for job in job_result.scalars().all()}
    else:
        jobs_by_id = {}

    interview_result = await db.execute(select(Interview).where(Interview.candidate_id == candidate_id))
    interviews = list(interview_result.scalars().all())

    interview_ids = [interview.id for interview in interviews]
    if interview_ids:
        feedback_result = await db.execute(
            select(InterviewEvaluation).where(InterviewEvaluation.interview_id.in_(interview_ids))
        )
        interview_feedback = list(feedback_result.scalars().all())
    else:
        interview_feedback = []

    rejection_result = await db.execute(
        select(CandidateRejectionRecord)
        .where(CandidateRejectionRecord.candidate_id == candidate_id)
        .order_by(CandidateRejectionRecord.created_at.asc())
    )
    rejections = list(rejection_result.scalars().all())

    profile_ids = sorted({record.job_profile_id for record in rejections if record.job_profile_id})
    if profile_ids:
        profile_result = await db.execute(select(JobProfile).where(JobProfile.id.in_(profile_ids)))
        job_profiles = list(profile_result.scalars().all())
    else:
        fallback_profile_result = await db.execute(
            select(JobProfile).where(JobProfile.code == "Java_P7", JobProfile.is_active.is_(True))
        )
        fallback_profile = fallback_profile_result.scalar_one_or_none()
        job_profiles = [fallback_profile] if fallback_profile else []

    missing_sections = []
    if not state_history:
        missing_sections.append("state_history")
    if not job_profiles:
        missing_sections.append("job_profiles")
    if not rejections:
        missing_sections.append("rejections")
    if not interviews:
        missing_sections.append("interviews")
    if not interview_feedback:
        missing_sections.append("interview_feedback")

    return success(
        {
            "candidate": {
                "id": candidate.id,
                "name": candidate.name,
                "status": _enum_value(candidate.status),
                "recruitment_state": _enum_value(candidate.recruitment_state),
            },
            "state_history": [
                {
                    "id": item.id,
                    "from_state": _enum_value(item.from_state) if item.from_state else None,
                    "to_state": _enum_value(item.to_state),
                    "reason": item.reason,
                    "operator_id": item.operator_id,
                    "triggered_actions": item.triggered_actions or [],
                    "metadata": item.metadata_,
                    "created_at": item.created_at,
                }
                for item in state_history
            ],
            "job_profiles": [
                {
                    "id": profile.id,
                    "code": profile.code,
                    "title": profile.title,
                    "level": profile.level,
                    "hard_requirements": profile.hard_requirements or [],
                    "soft_requirements": profile.soft_requirements or [],
                    "evaluation_dimensions": profile.evaluation_dimensions or [],
                    "interview_focus": profile.interview_focus or [],
                }
                for profile in job_profiles
            ],
            "applications": [
                {
                    "id": app.id,
                    "job_id": app.job_id,
                    "job_title": jobs_by_id.get(app.job_id).title if app.job_id in jobs_by_id else None,
                    "status": _enum_value(app.status),
                    "match_score": app.match_score,
                    "ai_summary": app.ai_summary,
                    "created_at": app.created_at,
                }
                for app in applications
            ],
            "interviews": [
                {
                    "id": interview.id,
                    "application_id": interview.application_id,
                    "type": _enum_value(interview.type),
                    "status": _enum_value(interview.status),
                    "scheduled_at": interview.scheduled_at,
                    "feedback": interview.feedback,
                }
                for interview in interviews
            ],
            "interview_feedback": [
                {
                    "id": feedback.id,
                    "interview_id": feedback.interview_id,
                    "round": _enum_value(feedback.round),
                    "overall_score": feedback.overall_score,
                    "verdict": _enum_value(feedback.verdict),
                    "dimensions": feedback.dimensions,
                    "key_observations": feedback.key_observations,
                    "red_flags": feedback.red_flags,
                    "feedback": feedback.feedback,
                    "created_at": feedback.created_at,
                }
                for feedback in interview_feedback
            ],
            "rejections": [
                {
                    "id": record.id,
                    "reason_code": record.reason_code,
                    "reason_category": record.reason_category,
                    "primary_reason": record.primary_reason,
                    "stage": record.stage,
                    "evidence": record.evidence,
                    "detail": record.detail,
                    "reusable_for_future": record.reusable_for_future,
                    "suggested_action": record.suggested_action,
                    "job_profile_id": record.job_profile_id,
                    "application_id": record.application_id,
                    "created_at": record.created_at,
                }
                for record in rejections
            ],
            "missing_sections": missing_sections,
        }
    )


@router.post("", status_code=201)
async def create_candidate(data: CandidateCreate, od=ORG_SCOPED_DEP):
    """创建候选人 (org-scoped, 自动挂当前 org_id)。"""
    org_ctx, db = od
    service = CandidateService(db)
    return success(await service.create(data, org_id=org_ctx.org_id))


@router.put("/{candidate_id}")
async def update_candidate(candidate_id: str, data: CandidateUpdate, od=ORG_SCOPED_DEP):
    """更新候选人 (RLS 自动隔离)。"""
    org_ctx, db = od
    service = CandidateService(db)
    candidate = await service.update(candidate_id, data)
    if not candidate:
        return error("候选人不存在", status_code=404)
    return success(candidate)


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: str, od=ORG_SCOPED_DEP):
    """删除候选人 (RLS 自动隔离)。"""
    org_ctx, db = od
    service = CandidateService(db)
    ok = await service.delete(candidate_id)
    if not ok:
        return error("候选人不存在", status_code=404)
    return success({"message": "候选人已删除"})


@router.get("/{candidate_id}/timeline")
async def candidate_timeline(candidate_id: str, od=ORG_SCOPED_DEP):
    """获取候选人全生命周期时间线。"""
    org_ctx, db = od
    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)

    events = []

    events.append(
        {
            "type": "created",
            "title": "候选人入库",
            "description": f"候选人 {candidate.name} 被添加至系统",
            "timestamp": candidate.created_at.isoformat() if candidate.created_at else "",
            "status": "completed",
            "metadata": {"source": candidate.source if hasattr(candidate, "source") else "manual"},
        }
    )

    from app.models.application import Application

    app_result = await db.execute(select(Application).where(Application.candidate_id == candidate_id))
    applications = list(app_result.scalars().all())
    for app in applications:
        from app.models.job_position import JobPosition

        job = None
        if app.job_id:
            job_result = await db.execute(select(JobPosition).where(JobPosition.id == app.job_id))
            job = job_result.scalar_one_or_none()
        events.append(
            {
                "type": "application",
                "title": f"投递职位: {job.title if job else '未知'}",
                "description": f"状态: {app.status}",
                "timestamp": app.created_at.isoformat() if app.created_at else "",
                "status": "completed" if app.status in ("offered", "hired", "rejected") else "in_progress",
                "metadata": {"status": app.status, "job_id": app.job_id},
            }
        )

    if hasattr(candidate, "evaluations") and candidate.evaluations:
        for ev in candidate.evaluations:
            events.append(
                {
                    "type": "evaluation",
                    "title": "AI 评估完成",
                    "description": f"评分: {ev.overall_score}/100",
                    "timestamp": ev.created_at.isoformat() if hasattr(ev, "created_at") and ev.created_at else "",
                    "status": "completed",
                    "metadata": {"score": ev.overall_score},
                }
            )

    from app.models.interview import Interview

    iv_result = await db.execute(select(Interview).where(Interview.candidate_id == candidate_id))
    interviews = list(iv_result.scalars().all())
    for iv in interviews:
        events.append(
            {
                "type": "interview",
                "title": f"{'面试安排' if iv.status == 'scheduled' else '面试完成'}",
                "description": f"类型: {iv.type}, 状态: {iv.status}",
                "timestamp": iv.scheduled_at.isoformat() if iv.scheduled_at else "",
                "status": "completed" if iv.status in ("completed", "cancelled") else "pending",
                "metadata": {"status": iv.status, "type": iv.type, "id": iv.id},
            }
        )

    from app.models.interview_evaluation import InterviewEvaluation

    try:
        ev_result = await db.execute(
            select(InterviewEvaluation).where(InterviewEvaluation.interview_id.in_([iv.id for iv in interviews]))
            if interviews
            else select(InterviewEvaluation).where(False)
        )
        evaluations = list(ev_result.scalars().all())
    except Exception:
        evaluations = []
    for ev in evaluations:
        events.append(
            {
                "type": "feedback",
                "title": "面试反馈提交",
                "description": (
                    f"总体评分: {ev.overall_score if hasattr(ev, 'overall_score') and ev.overall_score else 'N/A'}/10"
                ),
                "timestamp": ev.created_at.isoformat() if hasattr(ev, "created_at") and ev.created_at else "",
                "status": "completed",
                "metadata": {"score": ev.overall_score if hasattr(ev, "overall_score") else None},
            }
        )

    events.sort(key=lambda e: e.get("timestamp", ""), reverse=False)

    return success(
        {
            "candidate_id": candidate_id,
            "candidate_name": candidate.name,
            "events": events,
            "total": len(events),
        }
    )


@router.post("/{candidate_id}/state")
async def transition_candidate_state(
    candidate_id: str,
    data: CandidateStateTransitionRequest,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    service = CandidateStateService(db)
    try:
        candidate, history = await service.transition(
            candidate_id=candidate_id,
            new_state=data.new_state,
            reason=data.reason,
            operator_id=org_ctx.user_id,
            metadata=data.metadata,
        )
    except LookupError:
        return error("候选人不存在", status_code=404)
    except CandidateStateTransitionError as exc:
        return error(str(exc), status_code=400)

    return success(
        {
            "candidate_id": candidate.id,
            "from_state": history.from_state.value if history.from_state else None,
            "to_state": history.to_state.value,
            "triggered_actions": history.triggered_actions,
            "history_id": history.id,
        }
    )
