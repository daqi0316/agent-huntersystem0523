from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class JobProfileVersionStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class JobProfileRequirementType(enum.StrEnum):
    HARD = "hard"
    SOFT = "soft"


class JobProfile(Base):
    __tablename__ = "job_profiles"
    __table_args__ = (UniqueConstraint("code", name="uq_job_profiles_code"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    department: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    hard_requirements: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    soft_requirements: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evaluation_dimensions: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    salary_band: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    interview_focus: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class JobProfileVersion(Base):
    __tablename__ = "job_profile_versions"
    __table_args__ = (UniqueConstraint("job_profile_id", "version", name="uq_job_profile_versions_profile_version"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_profile_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[JobProfileVersionStatus] = mapped_column(
        enum_column(JobProfileVersionStatus, "job_profile_version_status"),
        nullable=False,
        default=JobProfileVersionStatus.DRAFT,
        index=True,
    )
    change_reason: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    activated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class JobProfileRequirementItem(Base):
    __tablename__ = "job_profile_requirement_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profile_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[JobProfileRequirementType] = mapped_column(
        enum_column(JobProfileRequirementType, "job_profile_requirement_type"), nullable=False, index=True
    )
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    must_have: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weight: Mapped[float | None] = mapped_column(Float)
    evidence_required: Mapped[str | None] = mapped_column(Text)
    red_flag_if_missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class JobProfileDimension(Base):
    __tablename__ = "job_profile_dimensions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profile_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    must_have: Mapped[str | None] = mapped_column(Text)
    key_questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    red_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
