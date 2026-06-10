"""P1-C: 入职后跟踪 — OnboardingTracking / OnboardingCheckpoint / ProbationFeedback。"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class OnboardingStatus(str, enum.Enum):
    PREBOARDING = "preboarding"
    ONBOARDED = "onboarded"
    PROBATION = "probation"
    PROBATION_PASSED = "probation_passed"
    PROBATION_FAILED = "probation_failed"
    RESIGNED = "resigned"


class OnboardingRiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CheckpointType(str, enum.Enum):
    DAY_1 = "day_1"
    DAY_7 = "day_7"
    MONTH_1 = "month_1"
    MONTH_3 = "month_3"
    MONTH_6 = "month_6"


class CheckpointStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    SKIPPED = "skipped"


class OnboardingTracking(Base):
    __tablename__ = "onboarding_trackings"
    __table_args__ = (
        Index("ix_onboarding_tracking_candidate", "candidate_id"),
        Index("ix_onboarding_tracking_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    manager_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mentor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[OnboardingStatus] = mapped_column(
        enum_column(OnboardingStatus, "onboarding_status"),
        nullable=False,
        default=OnboardingStatus.PREBOARDING,
        index=True,
    )
    risk_level: Mapped[OnboardingRiskLevel] = mapped_column(
        enum_column(OnboardingRiskLevel, "onboarding_risk_level"),
        nullable=False,
        default=OnboardingRiskLevel.LOW,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class OnboardingCheckpoint(Base):
    __tablename__ = "onboarding_checkpoints"
    __table_args__ = (
        Index("ix_onboarding_checkpoint_tracking", "onboarding_id"),
        Index("ix_onboarding_checkpoint_due", "due_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    onboarding_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("onboarding_trackings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checkpoint_type: Mapped[CheckpointType] = mapped_column(
        enum_column(CheckpointType, "onboarding_checkpoint_type"), nullable=False
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CheckpointStatus] = mapped_column(
        enum_column(CheckpointStatus, "onboarding_checkpoint_status"),
        nullable=False,
        default=CheckpointStatus.PENDING,
        index=True,
    )
    owner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ProbationFeedback(Base):
    __tablename__ = "probation_feedbacks"
    __table_args__ = (
        Index("ix_probation_feedback_onboarding", "onboarding_id"),
        Index("ix_probation_feedback_checkpoint", "checkpoint_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    onboarding_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("onboarding_trackings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checkpoint_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("onboarding_checkpoints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    culture_fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ramp_up_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    communication_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    retention_risk: Mapped[str | None] = mapped_column(String(32), nullable=True)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pass_probation: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
