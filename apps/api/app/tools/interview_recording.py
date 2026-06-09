from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.database import AsyncSessionLocal
from app.models.interview_evaluation import EvaluationVerdict, InterviewRound
from app.services.interview import InterviewService
from app.services.interview_recording import InterviewRecordingError, InterviewRecordingService
from app.tools.metadata import Capability, register_tool


class RecordingToolInput(BaseModel):
    interview_id: str = Field(..., min_length=1, description="面试 ID")
    recording_id: str = Field(..., min_length=1, description="录音记录 ID")


class CreateRecordingEvaluationInput(RecordingToolInput):
    candidate_name: str = Field(default="候选人", description="候选人姓名")
    job_title: str = Field(default="", description="岗位名称")
    round: str = Field(default="R1", description="面试轮次: R1/R2/R3/R4 或 enum value")


def _parse_interview_round(value: str) -> InterviewRound:
    if value in InterviewRound.__members__:
        return InterviewRound[value]
    return InterviewRound(value)


def _failed(code: str, message: str) -> dict[str, Any]:
    return {"status": "failed", "error": {"code": code, "message": message}}


async def _handle_get_recording_status(interview_id: str = "", recording_id: str = "") -> dict[str, Any]:
    if not interview_id or not recording_id:
        return _failed("VALIDATION_ERROR", "interview_id 和 recording_id 不能为空")

    async with AsyncSessionLocal() as db:
        svc = InterviewRecordingService(db)
        recording = await svc.get_recording(interview_id, recording_id)
        if not recording:
            return _failed("NOT_FOUND", "录音不存在")
        return {"status": "success", "data": svc.to_dict(recording)}


async def _handle_transcribe_recording(interview_id: str = "", recording_id: str = "") -> dict[str, Any]:
    if not interview_id or not recording_id:
        return _failed("VALIDATION_ERROR", "interview_id 和 recording_id 不能为空")

    async with AsyncSessionLocal() as db:
        svc = InterviewRecordingService(db)
        try:
            recording = await svc.transcribe_recording(interview_id, recording_id)
        except InterviewRecordingError as exc:
            return _failed(exc.code, exc.message)
        return {"status": "success", "data": svc.to_dict(recording)}


async def _handle_create_recording_evaluation(
    interview_id: str = "",
    recording_id: str = "",
    candidate_name: str = "候选人",
    job_title: str = "",
    round: str = "R1",
) -> dict[str, Any]:
    if not interview_id or not recording_id:
        return _failed("VALIDATION_ERROR", "interview_id 和 recording_id 不能为空")

    async with AsyncSessionLocal() as db:
        recording_svc = InterviewRecordingService(db)
        recording = await recording_svc.get_recording(interview_id, recording_id)
        if not recording:
            return _failed("NOT_FOUND", "录音不存在")
        if not recording.transcript_text:
            return _failed("NO_TRANSCRIPT", "录音尚未转写，不能生成面试评价")

        from app.agents.interview_agent import InterviewAgent

        agent = InterviewAgent()
        feedback = await agent.generate_feedback_from_transcript(
            candidate_name=candidate_name,
            transcript_text=recording.transcript_text,
            job_title=job_title,
        )
        if feedback.get("status") == "insufficient_data":
            return _failed("NO_TRANSCRIPT", "缺少转录文本，不能生成面试评价")

        try:
            round_enum = _parse_interview_round(round)
            verdict_enum = EvaluationVerdict(feedback.get("verdict") or EvaluationVerdict.CONSIDER.value)
        except ValueError:
            return _failed("VALIDATION_ERROR", "无效的面试轮次或评估结论")

        interview_svc = InterviewService(db)
        evidence_quotes = feedback.get("evidence_quotes") or []
        strengths = feedback.get("strengths") or []
        concerns = feedback.get("concerns") or []
        evaluation = await interview_svc.save_evaluation(
            interview_id=interview_id,
            round=round_enum,
            overall_score=feedback.get("overall_score"),
            verdict=verdict_enum,
            dimensions={
                "source": "interview_recording",
                "recording_id": recording.id,
                "model_status": feedback.get("status"),
                "strengths": strengths,
                "evidence_quotes": evidence_quotes,
            },
            key_observations="\n".join(str(x) for x in evidence_quotes[:5]),
            red_flags="\n".join(str(x) for x in concerns[:5]),
            feedback=feedback.get("feedback") or "",
        )
        return {
            "status": "success",
            "data": {
                "interview_id": interview_id,
                "recording_id": recording.id,
                "feedback": feedback,
                "evaluation": interview_svc._eval_to_dict(evaluation),
            },
        }


register_tool(
    "get_recording_status",
    capability=Capability.READ,
    input_model=RecordingToolInput,
    description="查询指定面试录音的上传/转录状态。",
    version="1.0.0",
    handler=_handle_get_recording_status,
)
register_tool(
    "transcribe_recording",
    capability=Capability.WRITE,
    input_model=RecordingToolInput,
    description="触发指定面试录音的 ASR 转录；幂等，已转写直接返回。",
    version="1.0.0",
    handler=_handle_transcribe_recording,
)
register_tool(
    "create_recording_evaluation",
    capability=Capability.WRITE,
    input_model=CreateRecordingEvaluationInput,
    description="基于已转录的面试录音生成结构化评价并写入 interview_evaluations。",
    version="1.0.0",
    handler=_handle_create_recording_evaluation,
)


tools = [
    {
        "type": "function",
        "function": {
            "name": "get_recording_status",
            "description": "查询指定面试录音的上传/转录状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "interview_id": {"type": "string", "description": "面试 ID"},
                    "recording_id": {"type": "string", "description": "录音记录 ID"},
                },
                "required": ["interview_id", "recording_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transcribe_recording",
            "description": "触发指定面试录音的 ASR 转录；幂等，已转写直接返回。",
            "parameters": {
                "type": "object",
                "properties": {
                    "interview_id": {"type": "string", "description": "面试 ID"},
                    "recording_id": {"type": "string", "description": "录音记录 ID"},
                },
                "required": ["interview_id", "recording_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_recording_evaluation",
            "description": "基于已转录的面试录音生成结构化评价并写入 interview_evaluations。",
            "parameters": {
                "type": "object",
                "properties": {
                    "interview_id": {"type": "string", "description": "面试 ID"},
                    "recording_id": {"type": "string", "description": "录音记录 ID"},
                    "candidate_name": {"type": "string", "description": "候选人姓名（默认 候选人）"},
                    "job_title": {"type": "string", "description": "岗位名称（可选）"},
                    "round": {"type": "string", "description": "面试轮次: R1/R2/R3/R4 或 enum value（默认 R1）"},
                },
                "required": ["interview_id", "recording_id"],
            },
        },
    },
]

handlers = {
    "get_recording_status": _handle_get_recording_status,
    "transcribe_recording": _handle_transcribe_recording,
    "create_recording_evaluation": _handle_create_recording_evaluation,
}
