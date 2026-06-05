"""Audit log schemas。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.audit_log import AuditLogAction


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    actor_user_id: Optional[str] = None
    action: AuditLogAction
    target_user_id: Optional[str] = None
    meta: dict = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime


class AuditLogList(BaseModel):
    items: list[AuditLogOut]
    total: int
