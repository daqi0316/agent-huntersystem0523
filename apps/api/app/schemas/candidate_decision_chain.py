from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    triggered_actions: list[dict[str, Any]]
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


class DecisionChainJobProfileSummary(BaseModel):
    id: str
    code: str
    title: str
    level: str
    hard_requirements: list[str]
    soft_requirements: list[str]
    evaluation_dimensions: list[dict[str, Any]]
    interview_focus: list[str]


class DecisionChainApplicationSummary(BaseModel):
    id: str
    job_id: str | None = None
    job_title: str | None = None
    job_profile_id: str | None = None
    profile_version_id: str | None = None
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


class DecisionChainScorecardSummary(BaseModel):
    id: str
    interview_id: str
    candidate_id: str
    application_id: str | None = None
    scorecard_template_id: str
    scorecard_template_name: str | None = None
    profile_version_id: str | None = None
    profile_version_is_current: bool = True
    interviewer_id: str
    overall_score: float
    verdict: str
    summary: str | None = None
    risk_flags: list[str]
    submitted_at: datetime | None = None
    dimension_scores: list[dict[str, Any]] = Field(default_factory=list)


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
    severity: str | None = None
    preventable_by: str | None = None
    stage_applicability: list[str] = Field(default_factory=list)
    source: str = "human"
    confidence: float | None = None
    is_primary: bool = True
    related_scorecard_submission_id: str | None = None
    related_dimension_id: str | None = None
    evidence_ref_id: str | None = None
    created_at: datetime | None = None


class DecisionChainTimelineEvidenceSummary(BaseModel):
    id: str
    event_type: str
    title: str
    content: str | None = None
    occurred_at: datetime | None = None
    source: str


class DecisionChainEvidenceRefSummary(BaseModel):
    id: str
    source_type: str
    normalized_claim: str
    confidence: float | None = None
    created_by_type: str
    quote: str | None = None
    created_at: datetime | None = None


class DecisionChainAiAuditSummary(BaseModel):
    id: str
    decision_type: str
    model_name: str
    output_summary: str
    confidence: float | None = None
    human_confirmed: bool = False
    created_at: datetime | None = None


class DecisionChainCompensationRiskSummary(BaseModel):
    has_expectation: bool = False
    expected_total: float | None = None
    minimum_acceptable: float | None = None
    current_total: float | None = None
    market_p50: float | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    risk_label: str | None = None
    risk_score: int | None = None
    gap_to_market_p50_pct: float | None = None
    gap_to_budget_max_pct: float | None = None
    reasons: list[str] = Field(default_factory=list)


class CandidateDecisionChainRead(BaseModel):
    candidate: DecisionChainCandidateSummary
    state_history: list[DecisionChainStateHistoryItem]
    job_profiles: list[DecisionChainJobProfileSummary]
    applications: list[DecisionChainApplicationSummary]
    interviews: list[DecisionChainInterviewSummary]
    interview_feedback: list[DecisionChainInterviewFeedbackSummary]
    scorecards: list[DecisionChainScorecardSummary]
    rejections: list[DecisionChainRejectionSummary]
    timeline_evidence: list[DecisionChainTimelineEvidenceSummary]
    evidence_refs: list[DecisionChainEvidenceRefSummary] = Field(default_factory=list)
    ai_audits: list[DecisionChainAiAuditSummary] = Field(default_factory=list)
    compensation_risk: DecisionChainCompensationRiskSummary = Field(default_factory=DecisionChainCompensationRiskSummary)
    missing_sections: list[str]


class CandidateDecisionChainResponse(BaseModel):
    success: bool
    data: CandidateDecisionChainRead
