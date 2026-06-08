from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class RecruitmentCandidateState(str, enum.Enum):
    """招聘深度状态机状态。

    不替换旧 ``CandidateStatus``。旧状态继续服务现有筛选/面试流程；本枚举用于
    深度招聘链路：岗位画像、结构化反馈、淘汰原因、Dashboard 漏斗。
    """

    NEW_APPLICATION = "new_application"
    SCREENING = "screening"
    SCREENING_PASSED = "screening_passed"
    SCREENING_REJECTED = "screening_rejected"
    FIRST_INTERVIEW_PENDING = "first_interview_pending"
    FIRST_INTERVIEW_SCHEDULED = "first_interview_scheduled"
    FIRST_INTERVIEW_FEEDBACK_PENDING = "first_interview_feedback_pending"
    FIRST_INTERVIEW_PASSED = "first_interview_passed"
    FIRST_INTERVIEW_REJECTED = "first_interview_rejected"
    SECOND_INTERVIEW_PENDING = "second_interview_pending"
    SECOND_INTERVIEW_SCHEDULED = "second_interview_scheduled"
    SECOND_INTERVIEW_FEEDBACK_PENDING = "second_interview_feedback_pending"
    SECOND_INTERVIEW_PASSED = "second_interview_passed"
    SECOND_INTERVIEW_REJECTED = "second_interview_rejected"
    OFFER_NEGOTIATION = "offer_negotiation"
    OFFER_SENT = "offer_sent"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_REJECTED = "offer_rejected"
    ONBOARDING_PENDING = "onboarding_pending"
    HIRED = "hired"
    PROBATION_TRACKING = "probation_tracking"
    PROBATION_PASSED = "probation_passed"
    PROBATION_REJECTED = "probation_rejected"


TERMINAL_RECRUITMENT_STATES = frozenset(
    {
        RecruitmentCandidateState.SCREENING_REJECTED,
        RecruitmentCandidateState.FIRST_INTERVIEW_REJECTED,
        RecruitmentCandidateState.SECOND_INTERVIEW_REJECTED,
        RecruitmentCandidateState.OFFER_REJECTED,
        RecruitmentCandidateState.PROBATION_PASSED,
        RecruitmentCandidateState.PROBATION_REJECTED,
    }
)


class CandidateStateHistory(Base):
    """候选人招聘状态流转历史。"""

    __tablename__ = "candidate_state_history"

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
    from_state: Mapped[RecruitmentCandidateState | None] = mapped_column(
        enum_column(RecruitmentCandidateState, "recruitment_candidate_state"),
        nullable=True,
    )
    to_state: Mapped[RecruitmentCandidateState] = mapped_column(
        enum_column(RecruitmentCandidateState, "recruitment_candidate_state"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    operator_id: Mapped[str] = mapped_column(String(255), nullable=False)
    triggered_actions: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
