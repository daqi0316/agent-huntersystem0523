from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DecisionChainCandidateSummary(BaseModel):
    id: str
    name: str
    status: str
    recruitment_state: str


class DecisionChainStateHistoryItem(BaseModel):
    id: str
    from_state: str | None = None
    to_state: str
    reason: str
    operator_id: str
    triggered_actions: list[dict]
    metadata: dict | None = None
    created_at: datetime | None = None


class DecisionChainJobProfileSummary(BaseModel):
    id: str
    code: str
    title: str
    level: str
    hard_requirements: list[str]
    soft_requirements: list[str]
    evaluation_dimensions: list[dict]
    interview_focus: list[str]


class DecisionChainApplicationSummary(BaseModel):
    id: str
    job_id: str | None = None
    job_title: str | None = None
    status: str
    match_score: float | None = None
    ai_summary: str | None = None
    created_at: datetime | None = None


class DecisionChainInterviewSummary(BaseModel):
    id: str
    application_id: str | None = None
    type: str
    status: str
    scheduled_at: datetime | None = None
    feedback: str | None = None


class DecisionChainInterviewFeedbackSummary(BaseModel):
    id: str
    interview_id: str
    round: str
    overall_score: float | None = None
    verdict: str
    dimensions: str | None = None
    key_observations: str | None = None
    red_flags: str | None = None
    feedback: str | None = None
    created_at: datetime | None = None


class DecisionChainRejectionSummary(BaseModel):
    id: str
    reason_code: str
    reason_category: str
    primary_reason: str
    stage: str
    evidence: str
    detail: str | None = None
    reusable_for_future: bool
    suggested_action: str | None = None
    job_profile_id: str | None = None
    application_id: str | None = None
    created_at: datetime | None = None


class CandidateDecisionChainRead(BaseModel):
    candidate: DecisionChainCandidateSummary
    state_history: list[DecisionChainStateHistoryItem]
    job_profiles: list[DecisionChainJobProfileSummary]
    applications: list[DecisionChainApplicationSummary]
    interviews: list[DecisionChainInterviewSummary]
    interview_feedback: list[DecisionChainInterviewFeedbackSummary]
    rejections: list[DecisionChainRejectionSummary]
    missing_sections: list[str]


class CandidateDecisionChainResponse(BaseModel):
    success: bool
    data: CandidateDecisionChainRead
