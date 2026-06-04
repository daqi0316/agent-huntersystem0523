"""面试 CRUD API — 安排、确认、取消、完成（含状态机闭环）+ 评价管理。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success, error
from app.schemas.application import ApplicationUpdate
from app.schemas.common import ListResponse
from app.services.application import ApplicationService
from app.services.candidate import CandidateService
from app.services.interview import InterviewService
from app.models.interview_evaluation import InterviewRound, EvaluationVerdict


class InterviewFromProposalRequest(BaseModel):
    """从 HumanLoop 面试提案创建面试记录。"""
    candidate_id: str = Field(..., description="候选人 ID")
    job_id: str = Field(..., description="职位 ID")
    scheduled_at: str | None = Field(None, description="ISO 8601 面试时间")
    type: str = Field("video", description="面试类型")
    duration_minutes: int = Field(60, ge=15)
    location: str | None = Field(None)
    notes: str | None = Field(None)


class EvaluationSaveRequest(BaseModel):
    round: str = Field("R1", description="面试轮次: R1/R2/R3/R4")
    overall_score: float | None = Field(None, ge=0, le=10)
    verdict: str = Field("consider", description="评估结论: strong_hire/hire/consider/pass")
    dimensions: dict | None = Field(None, description="各维度评分 JSON")
    key_observations: str | None = Field(None)
    red_flags: str | None = Field(None)
    feedback: str | None = Field(None)


class EvaluationFormRequest(BaseModel):
    candidate_name: str
    candidate_background: str = ""
    round_id: str = "R1"


class FeedbackSummaryRequest(BaseModel):
    candidate_name: str
    evaluations: list[dict] = []


router = APIRouter()


@router.get("", response_model=ListResponse)
async def list_interviews(
    date_from: datetime | None = Query(None, description="ISO datetime 起点（含）"),
    date_to: datetime | None = Query(None, description="ISO datetime 终点（不含）"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询面试列表，可选 date_from/date_to 时间窗过滤。"""
    service = InterviewService(db)
    items, total = await service.list_all(
        skip=skip, limit=limit, status=status, date_from=date_from, date_to=date_to,
    )
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{interview_id}")
async def get_interview(interview_id: str, db: AsyncSession = Depends(get_db)):
    """获取面试详情"""
    service = InterviewService(db)
    interview = await service._get_by_id(interview_id)
    if not interview:
        return error("面试不存在", status_code=404)
    return success(service._to_dict(interview))


@router.post("", status_code=201)
async def create_interview(
    candidate_id: str = Query(..., description="候选人 ID"),
    job_id: str = Query(..., description="职位 ID"),
    application_id: str | None = Query(None),
    type: str = Query("video", description="面试类型: video/phone/onsite/technical"),
    scheduled_at: str | None = Query(None, description="ISO 8601 时间"),
    duration_minutes: int = Query(60, ge=15),
    location: str | None = Query(None),
    notes: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """安排面试，含 slot 冲突检测"""
    service = InterviewService(db)
    slot = {
        "application_id": application_id or "",
        "type": type,
        "scheduled_at": scheduled_at or "",
        "duration_minutes": duration_minutes,
        "location": location or "",
        "notes": notes or "",
    }
    result = await service.schedule(candidate_id, job_id, slot)
    if result is None:
        return error("候选人不存在", status_code=404)
    if result.get("error"):
        return error(result["message"], status_code=409)
    return success(result)


@router.patch("/{interview_id}/confirm")
async def confirm_interview(interview_id: str, db: AsyncSession = Depends(get_db)):
    """确认面试"""
    service = InterviewService(db)
    result = await service.confirm(interview_id)
    if not result:
        return error("面试不存在", status_code=404)
    return success(result)


@router.patch("/{interview_id}/cancel")
async def cancel_interview(interview_id: str, db: AsyncSession = Depends(get_db)):
    """取消面试"""
    service = InterviewService(db)
    result = await service.cancel(interview_id)
    if not result:
        return error("面试不存在", status_code=404)
    return success(result)


@router.patch("/{interview_id}/complete")
async def complete_interview(
    interview_id: str,
    feedback: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """完成面试（附带反馈），自动流转候选人/申请状态机。

    闭环流程:
      面试 completed → 候选人 in_interview → completed
                     → 申请 interview → offer
    """
    interview_svc = InterviewService(db)
    result = await interview_svc.complete(interview_id, feedback or "")
    if not result:
        return error("面试不存在", status_code=404)

    candidate_svc = CandidateService(db)
    try:
        await candidate_svc.complete_interview(result.get("candidate_id", ""))
    except ValueError:
        pass

    app_svc = ApplicationService(db)
    apps, _ = await app_svc.list(
        candidate_id=result.get("candidate_id", ""),
        status="interview",
        limit=1,
    )
    if apps:
        await app_svc.update(apps[0]["id"], ApplicationUpdate(status="offer"))

    return success(result)


@router.post("/from-proposal", status_code=201)
async def create_interview_from_proposal(
    body: InterviewFromProposalRequest,
    db: AsyncSession = Depends(get_db),
):
    """从 HumanLoop 面试提案创建面试记录 + 状态流转 evaluated → in_interview。

    流程: HumanLoop 提案审批通过后调用此接口，
    创建面试记录同时自动更新候选人状态。
    """
    try:
        candidate_svc = CandidateService(db)
        if not await candidate_svc.move_to_interview(body.candidate_id):
            return error("候选人不存在", status_code=404)

        import uuid
        application_id = ""
        try:
            uuid.UUID(body.candidate_id)
            uuid.UUID(body.job_id)
            from app.models.application import Application
            from sqlalchemy import select
            app_row = await db.execute(
                select(Application).where(
                    Application.candidate_id == body.candidate_id,
                    Application.job_id == body.job_id,
                )
            )
            application = app_row.scalar_one_or_none()
            application_id = str(application.id) if application else ""
        except (ValueError, Exception):
            pass

        interview_svc = InterviewService(db)
        slot = {
            "type": body.type,
            "scheduled_at": body.scheduled_at or "",
            "duration_minutes": body.duration_minutes,
            "location": body.location or "",
            "notes": body.notes or "",
            "application_id": application_id,
        }
        result = await interview_svc.schedule(body.candidate_id, body.job_id, slot)
        if result is None:
            return error("候选人不存在", status_code=404)
        if result.get("error"):
            return error(result["message"], status_code=409)

        if application_id:
            app_svc = ApplicationService(db)
            await app_svc.update(application_id, ApplicationUpdate(status="interview"))

        return success(result)
    except ValueError as e:
        return error(str(e), status_code=400)


@router.get("/candidates/{candidate_id}/evaluations")
async def list_candidate_evaluations(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
):
    service = InterviewService(db)
    evals = await service.list_evaluations_by_candidate(candidate_id)
    return success(evals)


@router.get("/{interview_id}/evaluation")
async def get_interview_evaluations(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
):
    service = InterviewService(db)
    evals = await service.list_evaluations_by_candidate(interview_id)
    return success(evals)


@router.post("/{interview_id}/evaluation", status_code=201)
async def save_evaluation(
    interview_id: str,
    body: EvaluationSaveRequest,
    db: AsyncSession = Depends(get_db),
):
    service = InterviewService(db)
    try:
        round_enum = InterviewRound(body.round) if body.round else InterviewRound.R1
        verdict_enum = EvaluationVerdict(body.verdict) if body.verdict else EvaluationVerdict.CONSIDER
    except ValueError:
        return error("无效的面试轮次或评估结论", status_code=400)

    try:
        evaluation = await service.save_evaluation(
            interview_id=interview_id,
            round=round_enum,
            overall_score=body.overall_score,
            verdict=verdict_enum,
            dimensions=body.dimensions,
            key_observations=body.key_observations,
            red_flags=body.red_flags,
            feedback=body.feedback,
        )
    except ValueError as e:
        return error(str(e), status_code=404)

    return success(service._eval_to_dict(evaluation))


@router.post("/{interview_id}/evaluation/generate")
async def generate_evaluation_form(
    interview_id: str,
    body: EvaluationFormRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.agents.interview_agent import InterviewAgent
    agent = InterviewAgent()
    form = await agent.generate_evaluation_form(
        candidate_name=body.candidate_name,
        candidate_background=body.candidate_background,
        round_id=body.round_id,
    )
    return success({"interview_id": interview_id, "evaluation_form": form})


@router.post("/{interview_id}/evaluation/summarize")
async def summarize_feedback(
    interview_id: str,
    body: FeedbackSummaryRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.agents.interview_agent import InterviewAgent
    agent = InterviewAgent()
    summary = await agent.summarize_feedback(
        candidate_name=body.candidate_name,
        evaluations=body.evaluations,
    )
    return success({"interview_id": interview_id, "summary": summary})
