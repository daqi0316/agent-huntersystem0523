"""Task State — 长程任务全局状态定义。

对应 LangGraph 设计文档 §2.1 TaskState + 6 个子状态。
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from app.models.operation_log import OperationStatus


class ResumeParserSubState(TypedDict):
    content: str
    file_url: str
    parsed_data: dict | None
    confidence: float
    quality_score: int
    red_flags: list[dict]
    is_duplicate: bool
    needs_human_review: bool
    current_step: str
    error: str | None


class SourcingSubState(TypedDict):
    job_id: str
    skills: list[str]
    candidates_found: list[dict]
    current_step: str
    error: str | None


class ScreeningSubState(TypedDict):
    candidate_id: str
    job_id: str
    match_score: float
    screening_result: dict | None
    current_step: str
    error: str | None


class InterviewSubState(TypedDict):
    candidate_id: str
    job_id: str
    interview_scheduled: bool
    feedback: dict | None
    current_step: str
    error: str | None


class OfferSubState(TypedDict):
    candidate_id: str
    job_id: str
    salary_analysis: dict | None
    offer_created: bool
    current_step: str
    error: str | None


class OnboardingSubState(TypedDict):
    candidate_id: str
    employee_id: str | None
    tasks: list[dict]
    current_step: str
    error: str | None


class TaskState(TypedDict):
    task_id: str
    job_id: str
    user_id: str
    input_text: str
    status: str
    current_agent: str
    intent: str
    execution_history: list[dict]
    snapshot_id: str | None
    recovery_count: int
    resume_parser_state: dict | None
    sourcing_state: dict | None
    screening_state: dict | None
    interview_state: dict | None
    offer_state: dict | None
    onboarding_state: dict | None
    candidates: list[dict]
    messages: list[dict]
    shared_context: dict
    error: str | None


def make_initial_task_state(
    task_id: str = "",
    user_id: str = "",
    job_id: str = "",
    input_text: str = "",
) -> TaskState:
    return {
        "task_id": task_id,
        "job_id": job_id,
        "user_id": user_id,
        "input_text": input_text,
        "status": OperationStatus.PENDING.value,
        "current_agent": "",
        "intent": "",
        "execution_history": [],
        "snapshot_id": None,
        "recovery_count": 0,
        "resume_parser_state": None,
        "sourcing_state": None,
        "screening_state": None,
        "interview_state": None,
        "offer_state": None,
        "onboarding_state": None,
        "candidates": [],
        "messages": [{"role": "user", "content": input_text}] if input_text else [],
        "shared_context": {},
        "error": None,
    }
