import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
import enum

from app.models._base import enum_column


class InterviewStatus(str, enum.Enum):
    # 同 ApplicationStatus：DB label 大写、value 小写，保留裸 SAEnum（写 name）。
    # 详见 .omo/plans/decision-records/2026-06-03-enum-and-uuid-pattern.md
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class InterviewType(str, enum.Enum):
    # 同 ApplicationStatus
    PHONE = "phone"
    VIDEO = "video"
    ONSITE = "onsite"
    TECHNICAL = "technical"


class Interview(Base):
    __tablename__ = "interviews"

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
    application_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[InterviewType] = mapped_column(
        SAEnum(InterviewType, name="interview_type"),
        default=InterviewType.VIDEO,
    )
    status: Mapped[InterviewStatus] = mapped_column(
        SAEnum(InterviewStatus, name="interview_status"),
        default=InterviewStatus.SCHEDULED,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(default=60)
    location: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job_profile_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("job_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    profile_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("job_profile_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    candidate = relationship("Candidate", back_populates="interviews")
