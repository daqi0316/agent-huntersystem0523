"""Organization — 多租户顶层表。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum as SAEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class OrganizationPlan(str, enum.Enum):
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class OrganizationStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class Organization(Base):
    __tablename__ = "organization"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    slug: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[OrganizationPlan] = mapped_column(
        SAEnum(OrganizationPlan, name="organization_plan", values_callable=lambda x: [e.value for e in x]),
        default=OrganizationPlan.STARTER,
        nullable=False,
    )
    status: Mapped[OrganizationStatus] = mapped_column(
        SAEnum(OrganizationStatus, name="organization_status", values_callable=lambda x: [e.value for e in x]),
        default=OrganizationStatus.TRIAL,
        nullable=False,
    )

    quota_max_users: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    quota_max_candidates: Mapped[int] = mapped_column(
        Integer, default=1000, nullable=False
    )
    quota_max_storage_mb: Mapped[int] = mapped_column(
        Integer, default=5000, nullable=False
    )
    quota_llm_tokens_per_month: Mapped[int] = mapped_column(
        Integer, default=500_000, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_renews_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
