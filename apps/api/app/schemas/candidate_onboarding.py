"""P1-C: 入职后跟踪 schemas。"""
from datetime import date, datetime

from typing import Any

from pydantic import BaseModel, Field


class OnboardingTrackingCreate(BaseModel):
    candidate_id: str
    application_id: str | None = None
    offer_id: str | None = None
    hire_date: date | None = None
    department: str | None = None
    manager_id: str | None = None
    mentor_id: str | None = None
    status: str = "preboarding"
    risk_level: str = "low"


class OnboardingTrackingUpdate(BaseModel):
    status: str | None = None
    risk_level: str | None = None
    hire_date: date | None = None
    department: str | None = None
    manager_id: str | None = None
    mentor_id: str | None = None


class OnboardingCheckpointCreate(BaseModel):
    onboarding_id: str
    checkpoint_type: str
    due_at: datetime
    owner_id: str | None = None
    summary: str | None = None
    risk_flags: list[Any] = Field(default_factory=list)


class OnboardingCheckpointUpdate(BaseModel):
    status: str | None = None
    completed_at: datetime | None = None
    summary: str | None = None
    risk_flags: list[Any] | None = None


class ProbationFeedbackCreate(BaseModel):
    onboarding_id: str
    checkpoint_id: str | None = None
    reviewer_id: str | None = None
    performance_score: float | None = Field(None, ge=0, le=100)
    culture_fit_score: float | None = Field(None, ge=0, le=100)
    ramp_up_score: float | None = Field(None, ge=0, le=100)
    communication_score: float | None = Field(None, ge=0, le=100)
    retention_risk: str | None = None
    feedback_text: str | None = None
    pass_probation: bool | None = None


class ProbationFeedbackUpdate(BaseModel):
    performance_score: float | None = Field(None, ge=0, le=100)
    culture_fit_score: float | None = Field(None, ge=0, le=100)
    ramp_up_score: float | None = Field(None, ge=0, le=100)
    communication_score: float | None = Field(None, ge=0, le=100)
    retention_risk: str | None = None
    feedback_text: str | None = None
    pass_probation: bool | None = None
