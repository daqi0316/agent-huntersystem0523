from datetime import datetime

from pydantic import BaseModel, EmailStr


class CandidateCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    summary: str | None = None
    skills: list[str] = []
    experience_years: int | None = None
    education: str | None = None
    current_company: str | None = None
    current_title: str | None = None


class CandidateUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    summary: str | None = None
    skills: list[str] | None = None
    experience_years: int | None = None
    education: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    status: str | None = None


class CandidateRead(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None = None
    summary: str | None = None
    skills: list[str] = []
    experience_years: int | None = None
    education: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CandidateTimelineEventCreate(BaseModel):
    application_id: str | None = None
    event_type: str
    title: str
    content: str | None = None
    occurred_at: datetime | None = None
    source: str = "manual"
    metadata: dict = {}


class CandidateFollowupTaskCreate(BaseModel):
    application_id: str | None = None
    due_at: datetime
    task_type: str
    title: str
    priority: str = "medium"
    owner_id: str | None = None
    auto_generated: bool = False
    trigger_rule: str | None = None


class CandidateFollowupTaskUpdate(BaseModel):
    status: str


class CandidateCommitmentCreate(BaseModel):
    promised_by: str
    content: str
    due_at: datetime | None = None
    status: str = "open"
    related_event_id: str | None = None
