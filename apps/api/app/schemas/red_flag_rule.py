"""RedFlagRule schema — 红旗规则序列化。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RedFlagRuleCreate(BaseModel):
    job_profile_id: str | None = None
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    scope: str = Field(..., max_length=50)  # RedFlagScope value
    severity: str = Field("warning", max_length=20)
    condition_config: dict = Field(default_factory=dict)
    is_active: bool = True
    order_index: int = 0
    created_by: str = Field(..., min_length=1, max_length=255)


class RedFlagRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    scope: str | None = None
    severity: str | None = None
    condition_config: dict | None = None
    is_active: bool | None = None
    order_index: int | None = None


class RedFlagRuleRead(BaseModel):
    id: str
    job_profile_id: str | None = None
    name: str
    description: str | None = None
    scope: str
    severity: str
    condition_config: dict
    is_active: bool
    order_index: int
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
