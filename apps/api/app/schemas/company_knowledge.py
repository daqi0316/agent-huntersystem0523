"""P2-2: 公司专属招聘知识库 schemas。"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class KnowledgeItemCreate(BaseModel):
    """创建知识条目。"""
    org_id: str = Field(..., min_length=1, max_length=36)
    job_profile_id: str | None = None
    knowledge_type: str = Field(
        ...,
        pattern=r"^(interviewer_preference|team_culture|hiring_manager_preference|"
                r"historical_lesson|compensation_policy|rejection_pattern|"
                r"successful_profile|interview_question)$",
    )
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    source: str | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    effective_from: date | None = None
    effective_to: date | None = None
    tags: list[str] = Field(default_factory=list)
    created_by: str = Field(..., min_length=1)
    auto_generated: bool = False


class KnowledgeItemUpdate(BaseModel):
    """更新知识条目（不修改自动字段）。"""
    title: str | None = Field(None, min_length=1, max_length=255)
    content: str | None = None
    source: str | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    effective_from: date | None = None
    effective_to: date | None = None
    tags: list[str] | None = None
    status: str | None = Field(
        None,
        pattern=r"^(draft|proposed|active|expired|archived)$",
    )
    reviewed_by: str | None = None


class KnowledgeItemResponse(BaseModel):
    id: str
    org_id: str
    job_profile_id: str | None = None
    knowledge_type: str
    status: str
    title: str
    content: str
    source: str | None = None
    confidence: float | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    tags: list[str] = []
    embedding_id: str | None = None
    version: int = 1
    auto_generated: bool = False
    created_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class KnowledgeItemListParams(BaseModel):
    org_id: str
    knowledge_type: str | None = None
    status: str | None = None
    job_profile_id: str | None = None
    only_active: bool = False
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)
