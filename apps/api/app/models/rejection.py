from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class RejectionSeverity(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RejectionPreventableBy(enum.StrEnum):
    SOURCING = "sourcing"
    SCREENING = "screening"
    SCORECARD = "scorecard"
    COMPENSATION = "compensation"
    PROCESS = "process"
    NONE = "none"


class RejectionSource(enum.StrEnum):
    HUMAN = "human"
    AI = "ai"
    INTERVIEWER = "interviewer"
    SYSTEM = "system"


class RejectionReason(Base):
    __tablename__ = "rejection_reasons"
    __table_args__ = (UniqueConstraint("code", name="uq_rejection_reasons_code"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rejection_reasons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[RejectionSeverity] = mapped_column(
        enum_column(RejectionSeverity, "rejection_severity"),
        nullable=False,
        default=RejectionSeverity.MEDIUM,
        index=True,
    )
    stage_applicability: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    preventable_by: Mapped[RejectionPreventableBy] = mapped_column(
        enum_column(RejectionPreventableBy, "rejection_preventable_by"),
        nullable=False,
        default=RejectionPreventableBy.NONE,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CandidateRejectionRecord(Base):
    __tablename__ = "candidate_rejection_records"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_profile_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("job_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reason_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("rejection_reasons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason_category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    primary_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    reusable_for_future: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    source: Mapped[RejectionSource] = mapped_column(
        enum_column(RejectionSource, "rejection_source"), nullable=False, default=RejectionSource.HUMAN, index=True
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    related_scorecard_submission_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("interview_scorecard_submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    related_dimension_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("scorecard_dimensions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    operator_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
