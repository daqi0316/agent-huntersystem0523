from datetime import datetime

from pydantic import BaseModel


class ApplicationCreate(BaseModel):
    candidate_id: str
    job_id: str
    resume_url: str | None = None


class ApplicationUpdate(BaseModel):
    status: str | None = None
    match_score: float | None = None
    ai_summary: str | None = None


class ApplicationRead(BaseModel):
    id: str
    candidate_id: str
    job_id: str
    status: str
    match_score: float | None = None
    ai_summary: str | None = None
    resume_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationListRead(BaseModel):
    """带候选人姓名和职位名称的申请列表。"""
    id: str
    candidate_id: str
    job_id: str
    status: str
    match_score: float | None = None
    ai_summary: str | None = None
    resume_url: str | None = None
    candidate_name: str = ""
    job_title: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
