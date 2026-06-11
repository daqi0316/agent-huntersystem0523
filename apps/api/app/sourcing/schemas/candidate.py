from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourcingCandidateResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None
    current_company: str | None
    current_title: str | None
    skills: list[str]
    experience_years: int | None
    education: str | None
    summary: str | None
    sourcing_task_id: str | None
    source_platforms: list[str] | None
    source_urls: dict[str, Any] | None
    ai_analysis: dict[str, Any] | None
    match_scores: dict[str, Any] | None
    data_quality_score: float | None
    dedup_fingerprint: str | None
    last_crawled_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourcingCandidateDetailResponse(SourcingCandidateResponse):
    raw_data: dict[str, Any] | None
    logs: list[dict[str, Any]] = Field(default_factory=list, description="采集日志")


class CandidateMergeRequest(BaseModel):
    primary_id: str = Field(..., description="主候选人ID")
    merge_ids: list[str] = Field(..., min_length=1, description="被合并的候选人ID列表")


class CandidateAnalyzeRequest(BaseModel):
    jd_id: str | None = Field(default=None, description="关联JD ID，可选")
