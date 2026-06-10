import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column
from app.models.candidate_state import RecruitmentCandidateState
import enum


class CandidateStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    BLACKLISTED = "blacklisted"
    PENDING_EVAL = "pending_eval"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    IN_INTERVIEW = "in_interview"
    COMPLETED = "completed"
    FAILED = "failed"


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    summary: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    experience_years: Mapped[int | None] = mapped_column(Integer)
    education: Mapped[str | None] = mapped_column(Text)
    current_company: Mapped[str | None] = mapped_column(String(255))
    current_title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[CandidateStatus] = mapped_column(
        SAEnum(CandidateStatus, name="candidate_status", validate_strings=False, values_callable=lambda x: [e.value for e in x]),
        default=CandidateStatus.ACTIVE,
        index=True,
    )
    recruitment_state: Mapped[RecruitmentCandidateState] = mapped_column(
        enum_column(RecruitmentCandidateState, "recruitment_candidate_state"),
        default=RecruitmentCandidateState.NEW_APPLICATION,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    applications = relationship("Application", back_populates="candidate")
    interviews = relationship("Interview", back_populates="candidate")
