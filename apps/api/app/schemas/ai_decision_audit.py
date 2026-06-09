from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AiDecisionAuditCreate(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    application_id: str | None = None
    decision_type: str = Field(..., max_length=50)
    model_name: str = Field(..., max_length=128)
    prompt_version: str | None = Field(None, max_length=64)
    input_refs: dict = Field(default_factory=dict)
    output_summary: str = Field(..., min_length=1, max_length=8000)
    cited_standard_version_ids: list[str] = Field(default_factory=list)
    cited_evidence_ref_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(None, ge=0, le=1)


class AiDecisionAuditConfirm(BaseModel):
    confirmed_by: str = Field(..., min_length=1, max_length=255)
    confirmed_at: datetime | None = None


class AiDecisionAuditRead(BaseModel):
    id: str
    candidate_id: str
    application_id: str | None = None
    decision_type: str
    model_name: str
    prompt_version: str | None = None
    input_refs: dict
    output_summary: str
    cited_standard_version_ids: list[str]
    cited_evidence_ref_ids: list[str]
    confidence: float | None = None
    human_confirmed: bool = False
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
