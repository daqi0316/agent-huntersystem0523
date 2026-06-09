"""面试 CRUD API — 安排、确认、取消、完成（含状态机闭环）+ 评价管理。"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.org_context import org_scoped_db
from app.core.response import success, error
from app.schemas.application import ApplicationUpdate
from app.schemas.common import ListResponse
from app.services.application import ApplicationService
from app.services.candidate import CandidateService
from app.services.interview import InterviewService
from app.services.interview_recording import (
    InterviewRecordingError,
    InterviewRecordingService,
)
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


class RecordingFeedbackRequest(BaseModel):
    candidate_name: str = "候选人"
    job_title: str = ""
    round: str = "R1"


def _recording_error_response(exc: InterviewRecordingError):
    status_code = 404 if exc.code == "NOT_FOUND" else 400
    return error(exc.message, status_code=status_code)


def _parse_interview_round(value: str) -> InterviewRound:
    if value in InterviewRound.__members__:
        return InterviewRound[value]
    return InterviewRound(value)


router = APIRouter()


@router.get("", response_model=ListResponse)
async def list_interviews(
    date_from: datetime | None = Query(None, description="ISO datetime 起点（含）"),
    date_to: datetime | None = Query(None, description="ISO datetime 终点（不含）"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
    """分页查询面试列表，可选 date_from/date_to 时间窗过滤。"""
    service = InterviewService(db)
    items, total = await service.list_all(
        skip=skip, limit=limit, status=status, date_from=date_from, date_to=date_to,
    )
    return ListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{interview_id}")
async def get_interview(interview_id: str, od = Depends(org_scoped_db)):
    org_ctx, db = od
    """获取面试详情"""
    service = InterviewService(db)
    interview = await service._get_by_id(interview_id)
    if not interview:
        return error("面试不存在", status_code=404)
    return success(service._to_dict(interview))


@router.get("/{interview_id}/recordings")
async def list_interview_recordings(interview_id: str, od = Depends(org_scoped_db)):
    org_ctx, db = od
    service = InterviewRecordingService(db)
    interview = await InterviewService(db)._get_by_id(interview_id)
    if not interview:
        return error("面试不存在", status_code=404)
    recordings = await service.list_recordings(interview_id)
    return success([service.to_dict(r) for r in recordings])


@router.get("/{interview_id}/recordings/{recording_id}")
async def get_interview_recording(interview_id: str, recording_id: str, od = Depends(org_scoped_db)):
    org_ctx, db = od
    service = InterviewRecordingService(db)
    recording = await service.get_recording(interview_id, recording_id)
    if not recording:
        return error("录音不存在", status_code=404)
    return success(service.to_dict(recording))


@router.post("/{interview_id}/recordings/upload", status_code=201)
async def upload_interview_recording(
    interview_id: str,
    file: UploadFile = File(...),
    consent_confirmed: bool = Form(False),
    duration_seconds: float | None = Form(None),
    sample_rate: int | None = Form(None),
    channels: int | None = Form(None),
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
    file_bytes = await file.read()
    service = InterviewRecordingService(db)
    try:
        recording = await service.upload_recording(
            interview_id=interview_id,
            file_bytes=file_bytes,
            filename=file.filename or "recording.webm",
            mime_type=file.content_type or "",
            user_id=org_ctx.user_id,
            consent_confirmed=consent_confirmed,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            channels=channels,
        )
    except InterviewRecordingError as exc:
        return _recording_error_response(exc)
    return success(service.to_dict(recording))


@router.post("/{interview_id}/recordings/{recording_id}/transcribe")
async def transcribe_interview_recording(interview_id: str, recording_id: str, od = Depends(org_scoped_db)):
    org_ctx, db = od
    service = InterviewRecordingService(db)
    try:
        recording = await service.transcribe_recording(interview_id, recording_id)
    except InterviewRecordingError as exc:
        return _recording_error_response(exc)
    return success(service.to_dict(recording))


@router.post("/{interview_id}/recordings/{recording_id}/evaluation", status_code=201)
async def create_recording_evaluation(
    interview_id: str,
    recording_id: str,
    body: RecordingFeedbackRequest,
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
    recording_svc = InterviewRecordingService(db)
    recording = await recording_svc.get_recording(interview_id, recording_id)
    if not recording:
        return error("录音不存在", status_code=404)
    if not recording.transcript_text:
        return error("录音尚未转写，不能生成面试评价", status_code=400)

    from app.agents.interview_agent import InterviewAgent
    agent = InterviewAgent()
    feedback = await agent.generate_feedback_from_transcript(
        candidate_name=body.candidate_name,
        transcript_text=recording.transcript_text,
        job_title=body.job_title,
    )
    if feedback.get("status") == "insufficient_data":
        return error("缺少转录文本，不能生成面试评价", status_code=400)

    try:
        round_enum = _parse_interview_round(body.round) if body.round else InterviewRound.R1
        verdict_enum = EvaluationVerdict(feedback.get("verdict") or EvaluationVerdict.CONSIDER.value)
    except ValueError:
        return error("无效的面试轮次或评估结论", status_code=400)

    interview_svc = InterviewService(db)
    evidence_quotes = feedback.get("evidence_quotes") or []
    strengths = feedback.get("strengths") or []
    concerns = feedback.get("concerns") or []
    key_observations = "\n".join(str(x) for x in evidence_quotes[:5])
    red_flags = "\n".join(str(x) for x in concerns[:5])
    dimensions = {
        "source": "interview_recording",
        "recording_id": recording.id,
        "model_status": feedback.get("status"),
        "strengths": strengths,
        "evidence_quotes": evidence_quotes,
    }
    evaluation = await interview_svc.save_evaluation(
        interview_id=interview_id,
        round=round_enum,
        overall_score=feedback.get("overall_score"),
        verdict=verdict_enum,
        dimensions=dimensions,
        key_observations=key_observations,
        red_flags=red_flags,
        feedback=feedback.get("feedback") or "",
    )
    return success({
        "interview_id": interview_id,
        "recording_id": recording.id,
        "feedback": feedback,
        "evaluation": interview_svc._eval_to_dict(evaluation),
    })


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
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
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
async def confirm_interview(interview_id: str, od = Depends(org_scoped_db)):
    org_ctx, db = od
    """确认面试"""
    service = InterviewService(db)
    result = await service.confirm(interview_id)
    if not result:
        return error("面试不存在", status_code=404)
    return success(result)


@router.patch("/{interview_id}/cancel")
async def cancel_interview(interview_id: str, od = Depends(org_scoped_db)):
    org_ctx, db = od
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
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
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
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
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
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
    service = InterviewService(db)
    evals = await service.list_evaluations_by_candidate(candidate_id)
    return success(evals)


@router.get("/{interview_id}/evaluation")
async def get_interview_evaluations(
    interview_id: str,
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
    service = InterviewService(db)
    evals = await service.list_evaluations_by_candidate(interview_id)
    return success(evals)


@router.post("/{interview_id}/evaluation", status_code=201)
async def save_evaluation(
    interview_id: str,
    body: EvaluationSaveRequest,
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
    service = InterviewService(db)
    try:
        round_enum = _parse_interview_round(body.round) if body.round else InterviewRound.R1
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
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
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
    od = Depends(org_scoped_db),
):
    org_ctx, db = od
    from app.agents.interview_agent import InterviewAgent
    agent = InterviewAgent()
    summary = await agent.summarize_feedback(
        candidate_name=body.candidate_name,
        evaluations=body.evaluations,
    )
    return success({"interview_id": interview_id, "summary": summary})
