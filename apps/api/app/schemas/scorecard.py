from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ScorecardAnchorCreate(BaseModel):
    score: int = Field(..., ge=1, le=5)
    anchor_text: str = Field(..., min_length=1, max_length=4000)
    evidence_examples: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


class ScorecardDimensionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: str | None = Field(None, max_length=100)
    weight: float = Field(..., gt=0, le=1)
    description: str | None = None
    required: bool = True
    order_index: int = 0
    anchors: list[ScorecardAnchorCreate] = Field(default_factory=list)


class ScorecardTemplateCreate(BaseModel):
    job_profile_id: str | None = None
    profile_version_id: str | None = None
    name: str = Field(..., min_length=1, max_length=255)
    round_type: str = Field("technical", max_length=50)
    status: str = Field("draft", max_length=50)
    dimensions: list[ScorecardDimensionCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_weight_sum(self):
        total = sum(d.weight for d in self.dimensions)
        if abs(total - 1.0) > 0.001:
            raise ValueError("scorecard dimensions 权重总和必须等于 1.0")
        return self


class ScorecardFromJobProfileRequest(BaseModel):
    round_type: str = Field("technical", max_length=50)
    name: str | None = Field(None, max_length=255)
    status: str = Field("draft", max_length=50)


class ScorecardDimensionScoreCreate(BaseModel):
    dimension_id: str = Field(..., min_length=1)
    score: int = Field(..., ge=1, le=5)
    evidence: str = Field(..., min_length=1, max_length=4000)
    confidence: float | None = Field(None, ge=0, le=1)


class InterviewScorecardSubmissionCreate(BaseModel):
    scorecard_template_id: str = Field(..., min_length=1)
    verdict: str = Field("consider", max_length=50)
    summary: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    dimension_scores: list[ScorecardDimensionScoreCreate] = Field(..., min_length=1)


class ScorecardAnchorRead(ScorecardAnchorCreate):
    id: str
    dimension_id: str

    model_config = {"from_attributes": True}


class ScorecardDimensionRead(BaseModel):
    id: str
    scorecard_template_id: str
    name: str
    category: str | None = None
    weight: float
    description: str | None = None
    required: bool
    order_index: int
    anchors: list[ScorecardAnchorRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ScorecardTemplateRead(BaseModel):
    id: str
    job_profile_id: str | None = None
    profile_version_id: str | None = None
    name: str
    round_type: str
    status: str
    total_weight: float
    created_by: str
    created_at: datetime
    updated_at: datetime
    dimensions: list[ScorecardDimensionRead] = Field(default_factory=list)


class InterviewScorecardDimensionScoreRead(BaseModel):
    id: str
    submission_id: str
    dimension_id: str
    dimension_name: str | None = None
    score: int
    evidence: str
    confidence: float | None = None


class InterviewScorecardSubmissionRead(BaseModel):
    id: str
    interview_id: str
    candidate_id: str
    application_id: str | None = None
    scorecard_template_id: str
    interviewer_id: str
    overall_score: float
    verdict: str
    summary: str | None = None
    risk_flags: list[str]
    submitted_at: datetime
    dimension_scores: list[InterviewScorecardDimensionScoreRead] = Field(default_factory=list)
