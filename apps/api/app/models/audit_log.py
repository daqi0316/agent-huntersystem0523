"""AuditLog — P5-1 多租户审计日志。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AuditLogAction(str, enum.Enum):
    ORG_SWITCH = "org_switch"
    INVITE_ACCEPT = "invite_accept"
    MEMBERSHIP_ADD = "membership_add"
    MEMBERSHIP_REMOVE = "membership_remove"
    MEMBERSHIP_ROLE_CHANGE = "membership_role_change"


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actor_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    action: Mapped[AuditLogAction] = mapped_column(
        SAEnum(AuditLogAction, name="audit_log_action", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    target_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict, server_default="{}")
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
