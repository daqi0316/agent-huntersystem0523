from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceRefCreate(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    application_id: str | None = None
    source_type: str = Field(..., max_length=50)
    source_id: str | None = None
    quote: str | None = None
    normalized_claim: str = Field(..., min_length=1, max_length=4000)
    confidence: float | None = Field(None, ge=0, le=1)
    created_by_type: str = Field(..., max_length=20)
    created_by_id: str | None = None


class EvidenceRefRead(BaseModel):
    id: str
    candidate_id: str
    application_id: str | None = None
    source_type: str
    source_id: str | None = None
    quote: str | None = None
    normalized_claim: str
    confidence: float | None = None
    created_by_type: str
    created_by_id: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
