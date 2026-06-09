"""候选人 CRUD API + 生命周期时间线。"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.org_context import org_scoped_db
from app.core.response import error, success
from app.models.application import Application
from app.models.candidate_state import CandidateStateHistory
from app.models.candidate_timeline import (
    CandidateCommitment,
    CandidateCommitmentPromisedBy,
    CandidateCommitmentStatus,
    CandidateFollowupPriority,
    CandidateFollowupStatus,
    CandidateFollowupTask,
    CandidateTimelineEvent,
    CandidateTimelineEventType,
    CandidateTimelineSource,
)
from app.models.interview import Interview
from app.models.interview_evaluation import InterviewEvaluation
from app.models.job_position import JobPosition
from app.models.job_profile import JobProfile
from app.models.rejection import CandidateRejectionRecord
from app.models.scorecard import (
    InterviewScorecardDimensionScore,
    InterviewScorecardSubmission,
    ScorecardDimension,
    ScorecardTemplate,
)
from app.schemas.candidate import (
    CandidateCommitmentCreate,
    CandidateCreate,
    CandidateFollowupTaskCreate,
    CandidateFollowupTaskUpdate,
    CandidateRead,
    CandidateTimelineEventCreate,
    CandidateUpdate,
)
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


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _coerce_enum(enum_cls, value: str, field: str):
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_cls)
        raise ValueError(f"{field} 必须是: {allowed}") from exc


def _timeline_event_to_dict(event: CandidateTimelineEvent) -> dict:
    return {
        "id": event.id,
        "candidate_id": event.candidate_id,
        "application_id": event.application_id,
        "event_type": _enum_value(event.event_type),
        "title": event.title,
        "content": event.content,
        "occurred_at": event.occurred_at,
        "operator_id": event.operator_id,
        "source": _enum_value(event.source),
        "metadata": event.metadata_ or {},
        "created_at": event.created_at,
    }


def _followup_task_to_dict(task: CandidateFollowupTask) -> dict:
    return {
        "id": task.id,
        "candidate_id": task.candidate_id,
        "application_id": task.application_id,
        "due_at": task.due_at,
        "task_type": task.task_type,
        "title": task.title,
        "status": _enum_value(task.status),
        "priority": _enum_value(task.priority),
        "owner_id": task.owner_id,
        "auto_generated": task.auto_generated,
        "trigger_rule": task.trigger_rule,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _commitment_to_dict(commitment: CandidateCommitment) -> dict:
    return {
        "id": commitment.id,
        "candidate_id": commitment.candidate_id,
        "promised_by": _enum_value(commitment.promised_by),
        "content": commitment.content,
        "due_at": commitment.due_at,
        "status": _enum_value(commitment.status),
        "related_event_id": commitment.related_event_id,
        "created_at": commitment.created_at,
    }


async def _mark_overdue_followups(db, candidate_id: str) -> None:
    now = _now_utc()
    result = await db.execute(
        select(CandidateFollowupTask).where(
            CandidateFollowupTask.candidate_id == candidate_id,
            CandidateFollowupTask.status == CandidateFollowupStatus.PENDING,
            CandidateFollowupTask.due_at < now,
        )
    )
    changed = False
    for task in result.scalars().all():
        task.status = CandidateFollowupStatus.OVERDUE
        changed = True
    if changed:
        await db.commit()


async def _ensure_auto_followups(db, candidate_id: str, operator_id: str | None) -> None:
    pending_result = await db.execute(
        select(CandidateFollowupTask).where(
            CandidateFollowupTask.candidate_id == candidate_id,
            CandidateFollowupTask.status.in_([CandidateFollowupStatus.PENDING, CandidateFollowupStatus.OVERDUE]),
            CandidateFollowupTask.auto_generated.is_(True),
        )
    )
    existing_rules = {task.trigger_rule for task in pending_result.scalars().all()}
    events_result = await db.execute(
        select(CandidateTimelineEvent)
        .where(CandidateTimelineEvent.candidate_id == candidate_id)
        .order_by(CandidateTimelineEvent.occurred_at.desc())
    )
    events = list(events_result.scalars().all())
    if not events:
        return
    now = _now_utc()
    latest_event = events[0]
    generated: list[CandidateFollowupTask] = []
    if latest_event.occurred_at <= now - timedelta(days=3) and "no_reply_3d" not in existing_rules:
        generated.append(
            CandidateFollowupTask(
                candidate_id=candidate_id,
                application_id=latest_event.application_id,
                due_at=now,
                task_type="followup",
                title="候选人 3 天无回复，需跟进",
                priority=CandidateFollowupPriority.HIGH,
                owner_id=operator_id,
                auto_generated=True,
                trigger_rule="no_reply_3d",
            )
        )
    process_events = [
        event
        for event in events
        if event.event_type in {
            CandidateTimelineEventType.INTERVIEW,
            CandidateTimelineEventType.OFFER,
            CandidateTimelineEventType.APPLICATION,
            CandidateTimelineEventType.STATUS,
        }
    ]
    if (
        process_events
        and process_events[0].occurred_at <= now - timedelta(days=7)
        and "no_progress_7d" not in existing_rules
    ):
        generated.append(
            CandidateFollowupTask(
                candidate_id=candidate_id,
                application_id=process_events[0].application_id,
                due_at=now,
                task_type="process_check",
                title="7 天无流程进展，需检查招聘流程",
                priority=CandidateFollowupPriority.MEDIUM,
                owner_id=operator_id,
                auto_generated=True,
                trigger_rule="no_progress_7d",
            )
        )
    for event in events:
        if event.event_type == CandidateTimelineEventType.INTERVIEW:
            has_feedback = any(
                item.event_type == CandidateTimelineEventType.NOTE
                and (item.metadata_ or {}).get("related_interview_event_id") == event.id
                for item in events
            )
            feedback_rule = f"interview_feedback_24h:{event.id}"
            if (
                not has_feedback
                and event.occurred_at <= now - timedelta(hours=24)
                and feedback_rule not in existing_rules
            ):
                generated.append(
                    CandidateFollowupTask(
                        candidate_id=candidate_id,
                        application_id=event.application_id,
                        due_at=now,
                        task_type="interview_feedback",
                        title="面试后 24 小时未反馈，需提醒面试官",
                        priority=CandidateFollowupPriority.HIGH,
                        owner_id=operator_id,
                        auto_generated=True,
                        trigger_rule=feedback_rule,
                    )
                )
    for event in events:
        offer_rule = f"offer_response_48h:{event.id}"
        if (
            event.event_type == CandidateTimelineEventType.OFFER
            and event.occurred_at <= now - timedelta(hours=48)
            and offer_rule not in existing_rules
        ):
            generated.append(
                CandidateFollowupTask(
                    candidate_id=candidate_id,
                    application_id=event.application_id,
                    due_at=now,
                    task_type="offer_negotiation",
                    title="Offer 发出 48 小时无回应，需跟进谈判",
                    priority=CandidateFollowupPriority.URGENT,
                    owner_id=operator_id,
                    auto_generated=True,
                    trigger_rule=offer_rule,
                )
            )
    if generated:
        db.add_all(generated)
        await db.commit()


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
        scorecard_result = await db.execute(
            select(InterviewScorecardSubmission)
            .where(InterviewScorecardSubmission.interview_id.in_(interview_ids))
            .order_by(InterviewScorecardSubmission.submitted_at.asc())
        )
        scorecard_submissions = list(scorecard_result.scalars().all())
        scorecard_submission_ids = [submission.id for submission in scorecard_submissions]
        scorecard_template_ids = [submission.scorecard_template_id for submission in scorecard_submissions]
        if scorecard_submission_ids:
            dimension_score_result = await db.execute(
                select(InterviewScorecardDimensionScore).where(
                    InterviewScorecardDimensionScore.submission_id.in_(scorecard_submission_ids)
                )
            )
            scorecard_dimension_scores = list(dimension_score_result.scalars().all())
            dimension_ids = [score.dimension_id for score in scorecard_dimension_scores]
            if dimension_ids:
                dimension_result = await db.execute(
                    select(ScorecardDimension).where(ScorecardDimension.id.in_(dimension_ids))
                )
                scorecard_dimensions_by_id = {dimension.id: dimension for dimension in dimension_result.scalars().all()}
            else:
                scorecard_dimensions_by_id = {}
        else:
            scorecard_dimension_scores = []
            scorecard_dimensions_by_id = {}
        if scorecard_template_ids:
            template_result = await db.execute(
                select(ScorecardTemplate).where(ScorecardTemplate.id.in_(scorecard_template_ids))
            )
            scorecard_templates_by_id = {template.id: template for template in template_result.scalars().all()}
        else:
            scorecard_templates_by_id = {}
    else:
        interview_feedback = []
        scorecard_submissions = []
        scorecard_dimension_scores = []
        scorecard_dimensions_by_id = {}
        scorecard_templates_by_id = {}

    dimension_scores_by_submission: dict[str, list[InterviewScorecardDimensionScore]] = {}
    for score in scorecard_dimension_scores:
        dimension_scores_by_submission.setdefault(score.submission_id, []).append(score)

    rejection_result = await db.execute(
        select(CandidateRejectionRecord)
        .where(CandidateRejectionRecord.candidate_id == candidate_id)
        .order_by(CandidateRejectionRecord.created_at.asc())
    )
    rejections = list(rejection_result.scalars().all())

    timeline_result = await db.execute(
        select(CandidateTimelineEvent)
        .where(CandidateTimelineEvent.candidate_id == candidate_id)
        .order_by(CandidateTimelineEvent.occurred_at.asc())
    )
    timeline_events = list(timeline_result.scalars().all())
    timeline_evidence = [
        event for event in timeline_events
        if event.event_type in {
            CandidateTimelineEventType.INTERVIEW,
            CandidateTimelineEventType.OFFER,
            CandidateTimelineEventType.REJECTION,
            CandidateTimelineEventType.COMMITMENT,
            CandidateTimelineEventType.RISK,
        }
    ]

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
            "scorecards": [
                {
                    "id": submission.id,
                    "interview_id": submission.interview_id,
                    "candidate_id": submission.candidate_id,
                    "application_id": submission.application_id,
                    "scorecard_template_id": submission.scorecard_template_id,
                    "scorecard_template_name": scorecard_templates_by_id.get(submission.scorecard_template_id).name
                    if submission.scorecard_template_id in scorecard_templates_by_id
                    else None,
                    "profile_version_id": (
                        scorecard_templates_by_id.get(submission.scorecard_template_id).profile_version_id
                        if submission.scorecard_template_id in scorecard_templates_by_id
                        else None
                    ),
                    "interviewer_id": submission.interviewer_id,
                    "overall_score": submission.overall_score,
                    "verdict": _enum_value(submission.verdict),
                    "summary": submission.summary,
                    "risk_flags": submission.risk_flags or [],
                    "submitted_at": submission.submitted_at,
                    "dimension_scores": [
                        {
                            "id": score.id,
                            "dimension_id": score.dimension_id,
                            "dimension_name": scorecard_dimensions_by_id.get(score.dimension_id).name
                            if score.dimension_id in scorecard_dimensions_by_id
                            else None,
                            "score": score.score,
                            "evidence": score.evidence,
                            "confidence": score.confidence,
                        }
                        for score in dimension_scores_by_submission.get(submission.id, [])
                    ],
                }
                for submission in scorecard_submissions
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
            "timeline_evidence": [
                {
                    "id": event.id,
                    "event_type": _enum_value(event.event_type),
                    "title": event.title,
                    "content": event.content,
                    "occurred_at": event.occurred_at,
                    "source": _enum_value(event.source),
                }
                for event in timeline_evidence
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
    org_ctx, db = od
    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)

    await _mark_overdue_followups(db, candidate_id)

    events_result = await db.execute(
        select(CandidateTimelineEvent)
        .where(CandidateTimelineEvent.candidate_id == candidate_id)
        .order_by(CandidateTimelineEvent.occurred_at.asc())
    )
    stored_events = list(events_result.scalars().all())

    followups_result = await db.execute(
        select(CandidateFollowupTask)
        .where(CandidateFollowupTask.candidate_id == candidate_id)
        .order_by(CandidateFollowupTask.due_at.asc())
    )
    followups = list(followups_result.scalars().all())

    commitments_result = await db.execute(
        select(CandidateCommitment)
        .where(CandidateCommitment.candidate_id == candidate_id)
        .order_by(CandidateCommitment.created_at.asc())
    )
    commitments = list(commitments_result.scalars().all())

    events = [_timeline_event_to_dict(event) for event in stored_events]

    events.append(
        {
            "id": f"candidate-created:{candidate.id}",
            "type": "created",
            "event_type": "created",
            "title": "候选人入库",
            "content": f"候选人 {candidate.name} 被添加至系统",
            "description": f"候选人 {candidate.name} 被添加至系统",
            "occurred_at": candidate.created_at,
            "timestamp": candidate.created_at.isoformat() if candidate.created_at else "",
            "status": "completed",
            "metadata": {"source": candidate.source if hasattr(candidate, "source") else "manual"},
            "source": "system",
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
                "id": f"application:{app.id}",
                "type": "application",
                "event_type": "application",
                "title": f"投递职位: {job.title if job else '未知'}",
                "content": f"状态: {_enum_value(app.status)}",
                "description": f"状态: {_enum_value(app.status)}",
                "occurred_at": app.created_at,
                "timestamp": app.created_at.isoformat() if app.created_at else "",
                "status": "completed" if app.status in ("offered", "hired", "rejected") else "in_progress",
                "metadata": {"status": _enum_value(app.status), "job_id": app.job_id},
                "source": "system",
            }
        )

    if hasattr(candidate, "evaluations") and candidate.evaluations:
        for ev in candidate.evaluations:
            events.append(
                {
                    "id": f"evaluation:{ev.id}",
                    "type": "evaluation",
                    "event_type": "risk",
                    "title": "AI 评估完成",
                    "content": f"评分: {ev.overall_score}/100",
                    "description": f"评分: {ev.overall_score}/100",
                    "occurred_at": ev.created_at if hasattr(ev, "created_at") else None,
                    "timestamp": ev.created_at.isoformat() if hasattr(ev, "created_at") and ev.created_at else "",
                    "status": "completed",
                    "metadata": {"score": ev.overall_score},
                    "source": "ai",
                }
            )

    from app.models.interview import Interview

    iv_result = await db.execute(select(Interview).where(Interview.candidate_id == candidate_id))
    interviews = list(iv_result.scalars().all())
    for iv in interviews:
        events.append(
            {
                "id": f"interview:{iv.id}",
                "type": "interview",
                "event_type": "interview",
                "title": f"{'面试安排' if iv.status == 'scheduled' else '面试完成'}",
                "content": f"类型: {_enum_value(iv.type)}, 状态: {_enum_value(iv.status)}",
                "description": f"类型: {_enum_value(iv.type)}, 状态: {_enum_value(iv.status)}",
                "occurred_at": iv.scheduled_at,
                "timestamp": iv.scheduled_at.isoformat() if iv.scheduled_at else "",
                "status": "completed" if iv.status in ("completed", "cancelled") else "pending",
                "metadata": {"status": _enum_value(iv.status), "type": _enum_value(iv.type), "id": iv.id},
                "source": "system",
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
                "id": f"feedback:{ev.id}",
                "type": "feedback",
                "event_type": "note",
                "title": "面试反馈提交",
                "content": (
                    f"总体评分: {ev.overall_score if hasattr(ev, 'overall_score') and ev.overall_score else 'N/A'}/10"
                ),
                "description": (
                    f"总体评分: {ev.overall_score if hasattr(ev, 'overall_score') and ev.overall_score else 'N/A'}/10"
                ),
                "occurred_at": ev.created_at if hasattr(ev, "created_at") else None,
                "timestamp": ev.created_at.isoformat() if hasattr(ev, "created_at") and ev.created_at else "",
                "status": "completed",
                "metadata": {"score": ev.overall_score if hasattr(ev, "overall_score") else None},
                "source": "system",
            }
        )

    events.sort(key=lambda e: str(e.get("occurred_at") or e.get("timestamp") or ""), reverse=False)

    return success(
        {
            "candidate_id": candidate_id,
            "candidate_name": candidate.name,
            "events": events,
            "followup_tasks": [_followup_task_to_dict(task) for task in followups],
            "commitments": [_commitment_to_dict(commitment) for commitment in commitments],
            "overdue_count": sum(1 for task in followups if task.status == CandidateFollowupStatus.OVERDUE),
            "total": len(events),
        }
    )


@router.post("/{candidate_id}/timeline/events", status_code=201)
async def create_candidate_timeline_event(candidate_id: str, data: CandidateTimelineEventCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)
    try:
        event_type = _coerce_enum(CandidateTimelineEventType, data.event_type, "event_type")
        source = _coerce_enum(CandidateTimelineSource, data.source, "source")
    except ValueError as exc:
        return error(str(exc), status_code=400)
    event = CandidateTimelineEvent(
        candidate_id=candidate_id,
        application_id=data.application_id,
        event_type=event_type,
        title=data.title,
        content=data.content,
        occurred_at=data.occurred_at or _now_utc(),
        operator_id=org_ctx.user_id,
        source=source,
        metadata_=data.metadata,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    await _ensure_auto_followups(db, candidate_id, org_ctx.user_id)
    return success(_timeline_event_to_dict(event))


@router.post("/{candidate_id}/followup-tasks", status_code=201)
async def create_candidate_followup_task(candidate_id: str, data: CandidateFollowupTaskCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)
    try:
        priority = _coerce_enum(CandidateFollowupPriority, data.priority, "priority")
    except ValueError as exc:
        return error(str(exc), status_code=400)
    task = CandidateFollowupTask(
        candidate_id=candidate_id,
        application_id=data.application_id,
        due_at=data.due_at,
        task_type=data.task_type,
        title=data.title,
        priority=priority,
        owner_id=data.owner_id or org_ctx.user_id,
        auto_generated=data.auto_generated,
        trigger_rule=data.trigger_rule,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return success(_followup_task_to_dict(task))


@router.patch("/{candidate_id}/followup-tasks/{task_id}")
async def update_candidate_followup_task(
    candidate_id: str,
    task_id: str,
    data: CandidateFollowupTaskUpdate,
    od=ORG_SCOPED_DEP,
):
    org_ctx, db = od
    try:
        status = _coerce_enum(CandidateFollowupStatus, data.status, "status")
    except ValueError as exc:
        return error(str(exc), status_code=400)
    result = await db.execute(
        select(CandidateFollowupTask).where(
            CandidateFollowupTask.id == task_id,
            CandidateFollowupTask.candidate_id == candidate_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        return error("跟进任务不存在", status_code=404)
    task.status = status
    await db.commit()
    await db.refresh(task)
    return success(_followup_task_to_dict(task))


@router.post("/{candidate_id}/commitments", status_code=201)
async def create_candidate_commitment(candidate_id: str, data: CandidateCommitmentCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)
    try:
        promised_by = _coerce_enum(CandidateCommitmentPromisedBy, data.promised_by, "promised_by")
        status = _coerce_enum(CandidateCommitmentStatus, data.status, "status")
    except ValueError as exc:
        return error(str(exc), status_code=400)
    commitment = CandidateCommitment(
        candidate_id=candidate_id,
        promised_by=promised_by,
        content=data.content,
        due_at=data.due_at,
        status=status,
        related_event_id=data.related_event_id,
    )
    db.add(commitment)
    await db.commit()
    await db.refresh(commitment)
    return success(_commitment_to_dict(commitment))


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
