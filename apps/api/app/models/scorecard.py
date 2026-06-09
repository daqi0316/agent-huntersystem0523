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


class ScorecardStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ScorecardRoundType(enum.StrEnum):
    PHONE_SCREEN = "phone_screen"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    FINAL = "final"
    MANAGER = "manager"


class ScorecardVerdict(enum.StrEnum):
    STRONG_HIRE = "strong_hire"
    HIRE = "hire"
    CONSIDER = "consider"
    PASS = "pass"


class ScorecardTemplate(Base):
    __tablename__ = "scorecard_templates"
    __table_args__ = (
        UniqueConstraint(
            "job_profile_id",
            "round_type",
            "name",
            name="uq_scorecard_templates_profile_round_name",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_profile_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    profile_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profile_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    round_type: Mapped[ScorecardRoundType] = mapped_column(
        enum_column(ScorecardRoundType, "scorecard_round_type"), nullable=False, index=True
    )
    status: Mapped[ScorecardStatus] = mapped_column(
        enum_column(ScorecardStatus, "scorecard_status"), nullable=False, default=ScorecardStatus.DRAFT, index=True
    )
    total_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ScorecardDimension(Base):
    __tablename__ = "scorecard_dimensions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    scorecard_template_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("scorecard_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ScorecardBehaviorAnchor(Base):
    __tablename__ = "scorecard_behavior_anchors"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    dimension_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("scorecard_dimensions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_examples: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    red_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class InterviewScorecardSubmission(Base):
    __tablename__ = "interview_scorecard_submissions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scorecard_template_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("scorecard_templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    interviewer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    verdict: Mapped[ScorecardVerdict] = mapped_column(
        enum_column(ScorecardVerdict, "scorecard_verdict"), nullable=False, default=ScorecardVerdict.CONSIDER
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewScorecardDimensionScore(Base):
    __tablename__ = "interview_scorecard_dimension_scores"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    submission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("interview_scorecard_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dimension_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("scorecard_dimensions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
