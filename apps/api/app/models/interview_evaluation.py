import uuid
from datetime import datetime
import enum

from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class InterviewRound(str, enum.Enum):
    R1 = "phone_screen"
    R2 = "technical"
    R3 = "behavioral"
    R4 = "final"


class EvaluationVerdict(str, enum.Enum):
    STRONG_HIRE = "strong_hire"
    HIRE = "hire"
    CONSIDER = "consider"
    PASS = "pass"


class InterviewEvaluation(Base):
    __tablename__ = "interview_evaluations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    interview_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    round: Mapped[InterviewRound] = mapped_column(
        enum_column(InterviewRound, "interview_round"), default=InterviewRound.R1,
    )
    interviewer_id: Mapped[str | None] = mapped_column(String(255))
    overall_score: Mapped[float | None] = mapped_column(Float)
    verdict: Mapped[EvaluationVerdict] = mapped_column(
        enum_column(EvaluationVerdict, "evaluation_verdict"), default=EvaluationVerdict.CONSIDER,
    )
    dimensions: Mapped[str | None] = mapped_column(Text)  # JSON string
    key_observations: Mapped[str | None] = mapped_column(Text)
    red_flags: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
