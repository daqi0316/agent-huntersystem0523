from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ScoreAnchor(BaseModel):
    score: int = Field(..., ge=1, le=5)
    evidence: str = Field(..., min_length=1, max_length=1000)


class EvaluationDimension(BaseModel):
    dimension: str = Field(..., min_length=1, max_length=100)
    weight: float = Field(..., gt=0, le=1)
    must_have: str | None = Field(None, max_length=1000)
    key_questions: list[str] = Field(default_factory=list)
    scoring_guide: list[ScoreAnchor] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


class SalaryBand(BaseModel):
    base_min: int | None = Field(None, ge=0)
    base_max: int | None = Field(None, ge=0)
    total_min: int | None = Field(None, ge=0)
    total_max: int | None = Field(None, ge=0)
    currency: str = Field("CNY", max_length=10)
    period: str = Field("monthly", max_length=20)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.base_min is not None and self.base_max is not None and self.base_min > self.base_max:
            raise ValueError("base_min 不能大于 base_max")
        if self.total_min is not None and self.total_max is not None and self.total_min > self.total_max:
            raise ValueError("total_min 不能大于 total_max")
        return self


class JobProfileBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    level: str = Field(..., min_length=1, max_length=50)
    department: str | None = Field(None, max_length=255)
    description: str | None = None
    hard_requirements: list[str] = Field(default_factory=list)
    soft_requirements: list[str] = Field(default_factory=list)
    evaluation_dimensions: list[EvaluationDimension] = Field(default_factory=list)
    salary_band: SalaryBand = Field(default_factory=SalaryBand)
    interview_focus: list[str] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_dimension_weights(self):
        if not self.evaluation_dimensions:
            return self
        total = sum(d.weight for d in self.evaluation_dimensions)
        if abs(total - 1.0) > 0.001:
            raise ValueError("evaluation_dimensions 权重总和必须等于 1.0")
        return self


class JobProfileCreate(JobProfileBase):
    pass


class JobProfileUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    level: str | None = Field(None, min_length=1, max_length=50)
    department: str | None = Field(None, max_length=255)
    description: str | None = None
    hard_requirements: list[str] | None = None
    soft_requirements: list[str] | None = None
    evaluation_dimensions: list[EvaluationDimension] | None = None
    salary_band: SalaryBand | None = None
    interview_focus: list[str] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_dimension_weights(self):
        if self.evaluation_dimensions is None:
            return self
        total = sum(d.weight for d in self.evaluation_dimensions)
        if abs(total - 1.0) > 0.001:
            raise ValueError("evaluation_dimensions 权重总和必须等于 1.0")
        return self


class JobProfileRead(JobProfileBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobProfileVersionCreate(BaseModel):
    change_reason: str | None = None
    status: str = Field("draft", max_length=50)


class JobProfileRequirementItemRead(BaseModel):
    id: str
    profile_version_id: str
    type: str
    category: str | None = None
    label: str
    description: str | None = None
    must_have: bool
    weight: float | None = None
    evidence_required: str | None = None
    red_flag_if_missing: bool
    order_index: int


class JobProfileDimensionRead(BaseModel):
    id: str
    profile_version_id: str
    name: str
    category: str | None = None
    weight: float
    description: str | None = None
    must_have: str | None = None
    key_questions: list[str]
    red_flags: list[str]
    order_index: int


class JobProfileVersionRead(BaseModel):
    id: str
    job_profile_id: str
    version: int
    status: str
    change_reason: str | None = None
    snapshot: dict
    created_by: str
    created_at: datetime
    requirements: list[JobProfileRequirementItemRead] = Field(default_factory=list)
    dimensions: list[JobProfileDimensionRead] = Field(default_factory=list)
