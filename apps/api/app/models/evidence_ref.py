from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class EvidenceSourceType(str, enum.Enum):
    RESUME = "resume"
    INTERVIEW = "interview"
    SCORECARD = "scorecard"
    REJECTION = "rejection"
    TIMELINE = "timeline"
    COMPENSATION = "compensation"
    ONBOARDING = "onboarding"
    KNOWLEDGE = "knowledge"


class EvidenceCreatedByType(str, enum.Enum):
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"


class EvidenceRef(Base):
    __tablename__ = "evidence_refs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_type: Mapped[EvidenceSourceType] = mapped_column(
        enum_column(EvidenceSourceType, "evidence_source_type"), nullable=False, index=True
    )
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_claim: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )
    created_by_type: Mapped[EvidenceCreatedByType] = mapped_column(
        enum_column(EvidenceCreatedByType, "evidence_created_by_type"), nullable=False, default=EvidenceCreatedByType.HUMAN
    )
    created_by_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_evidence_refs_confidence_range",
        ),
    )
