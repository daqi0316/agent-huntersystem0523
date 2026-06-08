from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


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
