from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RejectionReasonCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    parent_id: str | None = None
    category: str = Field(..., min_length=1, max_length=100)
    label: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    severity: str = Field("medium", max_length=20)
    stage_applicability: list[str] = Field(default_factory=list)
    preventable_by: str = Field("none", max_length=50)
    is_active: bool = True


class RejectionReasonRead(RejectionReasonCreate):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CandidateRejectRequest(BaseModel):
    reason_code: str = Field(..., min_length=1, max_length=64)
    stage: str = Field(..., min_length=1, max_length=100)
    evidence: str = Field(..., min_length=1, max_length=4000)
    application_id: str | None = None
    job_profile_id: str | None = None
    detail: str | None = None
    reusable_for_future: bool = False
    suggested_action: str | None = None
    metadata: dict | None = None
    source: str = Field("human", max_length=50)
    confidence: float | None = Field(None, ge=0, le=1)
    is_primary: bool = True
    related_scorecard_submission_id: str | None = None
    related_dimension_id: str | None = None


class CandidateRejectionRecordRead(BaseModel):
    id: str
    candidate_id: str
    application_id: str | None = None
    job_profile_id: str | None = None
    reason_id: str | None = None
    reason_code: str
    reason_category: str
    primary_reason: str
    stage: str
    evidence: str
    detail: str | None = None
    reusable_for_future: bool
    suggested_action: str | None = None
    metadata: dict | None = None
    source: str = "human"
    confidence: float | None = None
    is_primary: bool = True
    related_scorecard_submission_id: str | None = None
    related_dimension_id: str | None = None
    operator_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RejectionAnalyticsItem(BaseModel):
    key: str
    label: str
    count: int
    percentage: float


class RejectionAnalyticsRead(BaseModel):
    total: int
    by_reason: list[RejectionAnalyticsItem]
    by_stage: list[RejectionAnalyticsItem]
    by_job_profile: list[RejectionAnalyticsItem]
    by_preventable_by: list[RejectionAnalyticsItem]
