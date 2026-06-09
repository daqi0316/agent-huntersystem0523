from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class AiDecisionType(str, enum.Enum):
    SCREENING = "screening"
    SCORECARD_ASSIST = "scorecard_assist"
    REJECTION_SUGGEST = "rejection_suggest"
    OFFER_RISK = "offer_risk"
    ONBOARDING_RISK = "onboarding_risk"
    PROFILE_SUGGESTION = "profile_suggestion"


class AiDecisionAudit(Base):
    __tablename__ = "ai_decision_audits"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decision_type: Mapped[AiDecisionType] = mapped_column(
        enum_column(AiDecisionType, "ai_decision_type"), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_refs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_summary: Mapped[str] = mapped_column(Text, nullable=False)
    cited_standard_version_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cited_evidence_ref_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    human_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
