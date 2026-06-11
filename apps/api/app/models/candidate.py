import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, Float, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID, JSON
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
    # === NEW: 寻源扩展 (全 nullable, 无损兼容) ===
    sourcing_task_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="来源采集任务ID"
    )
    source_platforms: Mapped[list | None] = mapped_column(
        ARRAY(String), nullable=True, comment="来源平台列表"
    )
    source_urls: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="各平台 URL {boss_zhipin: url, ...}"
    )
    raw_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="各平台原始解析数据 {boss_zhipin: {...}}"
    )
    ai_analysis: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="AI 分析结果缓存"
    )
    match_scores: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="按岗位匹配分 {job_id: score}"
    )
    data_quality_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="数据质量评分 0-1"
    )
    dedup_fingerprint: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="去重指纹"
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="上次采集时间"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    applications = relationship("Application", back_populates="candidate")
    interviews = relationship("Interview", back_populates="candidate")
