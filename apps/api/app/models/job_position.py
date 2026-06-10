import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
import enum


class JobStatus(str, enum.Enum):
    # 同 ApplicationStatus：DB label 大写、value 小写，保留裸 SAEnum（写 name）。
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class JobPosition(Base):
    __tablename__ = "job_positions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    department: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    salary_range: Mapped[str | None] = mapped_column(String(100))
    job_profile_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    profile_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profile_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status"),
        default=JobStatus.DRAFT,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    applications = relationship("Application", back_populates="job")
