from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class CandidateTimelineEventType(str, enum.Enum):
    CALL = "call"
    WECHAT = "wechat"
    EMAIL = "email"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTION = "rejection"
    FOLLOWUP = "followup"
    NOTE = "note"
    COMMITMENT = "commitment"
    RISK = "risk"
    APPLICATION = "application"
    STATUS = "status"


class CandidateTimelineSource(str, enum.Enum):
    MANUAL = "manual"
    SYSTEM = "system"
    AI = "ai"
    INTEGRATION = "integration"


class CandidateFollowupStatus(str, enum.Enum):
    PENDING = "pending"
    DONE = "done"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class CandidateFollowupPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class CandidateCommitmentPromisedBy(str, enum.Enum):
    CANDIDATE = "candidate"
    RECRUITER = "recruiter"
    INTERVIEWER = "interviewer"
    HIRING_MANAGER = "hiring_manager"


class CandidateCommitmentStatus(str, enum.Enum):
    OPEN = "open"
    FULFILLED = "fulfilled"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class CandidateTimelineEvent(Base):
    __tablename__ = "candidate_timeline_events"
    __table_args__ = (
        Index("ix_candidate_timeline_candidate_occurred", "candidate_id", "occurred_at"),
        Index("ix_candidate_timeline_application", "application_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[CandidateTimelineEventType] = mapped_column(
        enum_column(CandidateTimelineEventType, "candidate_timeline_event_type"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    operator_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[CandidateTimelineSource] = mapped_column(
        enum_column(CandidateTimelineSource, "candidate_timeline_source"), nullable=False, default=CandidateTimelineSource.MANUAL
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CandidateFollowupTask(Base):
    __tablename__ = "candidate_followup_tasks"
    __table_args__ = (
        Index("ix_candidate_followup_status_due", "status", "due_at"),
        Index("ix_candidate_followup_candidate_due", "candidate_id", "due_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CandidateFollowupStatus] = mapped_column(
        enum_column(CandidateFollowupStatus, "candidate_followup_status"),
        nullable=False,
        default=CandidateFollowupStatus.PENDING,
        index=True,
    )
    priority: Mapped[CandidateFollowupPriority] = mapped_column(
        enum_column(CandidateFollowupPriority, "candidate_followup_priority"),
        nullable=False,
        default=CandidateFollowupPriority.MEDIUM,
    )
    owner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    trigger_rule: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CandidateCommitment(Base):
    __tablename__ = "candidate_commitments"
    __table_args__ = (Index("ix_candidate_commitments_candidate_due", "candidate_id", "due_at"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    promised_by: Mapped[CandidateCommitmentPromisedBy] = mapped_column(
        enum_column(CandidateCommitmentPromisedBy, "candidate_commitment_promised_by"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CandidateCommitmentStatus] = mapped_column(
        enum_column(CandidateCommitmentStatus, "candidate_commitment_status"),
        nullable=False,
        default=CandidateCommitmentStatus.OPEN,
        index=True,
    )
    related_event_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("candidate_timeline_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
