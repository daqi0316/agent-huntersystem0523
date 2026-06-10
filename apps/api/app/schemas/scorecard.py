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

    @model_validator(mode="after")
    def validate_required_behavior_anchors(self):
        scores = {anchor.score for anchor in self.anchors}
        missing = {1, 3, 5} - scores
        if missing:
            raise ValueError("每个评分维度必须提供 1/3/5 行为锚定")
        return self


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


class ScorecardTemplateUpdate(BaseModel):
    """更新 draft 评分卡模板（仅 draft 状态允许编辑）。"""
    name: str | None = Field(None, min_length=1, max_length=255)
    round_type: str | None = Field(None, max_length=50)
    dimensions: list[ScorecardDimensionCreate] | None = None

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if self.name is None and self.round_type is None and self.dimensions is None:
            raise ValueError("至少提供一个待更新字段")
        if self.dimensions is not None:
            if len(self.dimensions) < 1:
                raise ValueError("至少提供一个评分维度")
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
    evidence_ref_id: str | None = None

    @model_validator(mode="after")
    def validate_low_high_score_confidence(self):
        if self.score <= 2 and self.confidence is None:
            raise ValueError("低分（≤2）必须提供 confidence")
        if self.score == 5 and self.confidence is None:
            raise ValueError("高分（=5）必须提供 confidence")
        return self


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
    evidence_ref_id: str | None = None


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
