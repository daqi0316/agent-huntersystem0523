"""P2-2: 公司专属招聘知识库 — CompanyRecruitingKnowledgeItem。

在现有 Qdrant RAG 基础之上加一层结构化知识管理：
- 可引用（AI 输出必须引用知识来源）
- 可过期（effective_from/effective_to）
- 可版本化
- 人工确认后才能成为 active 知识
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class KnowledgeItemType(str, enum.Enum):
    INTERVIEWER_PREFERENCE = "interviewer_preference"
    TEAM_CULTURE = "team_culture"
    HIRING_MANAGER_PREFERENCE = "hiring_manager_preference"
    HISTORICAL_LESSON = "historical_lesson"
    COMPENSATION_POLICY = "compensation_policy"
    REJECTION_PATTERN = "rejection_pattern"
    SUCCESSFUL_PROFILE = "successful_profile"
    INTERVIEW_QUESTION = "interview_question"


class KnowledgeItemStatus(str, enum.Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class CompanyRecruitingKnowledgeItem(Base):
    """公司专属招聘知识条目。

    硬规则：
    - AI 输出必须引用知识来源（通过 evidence_refs）
    - 过期知识（effective_to < now）不得参与 AI 判断
    - 自动沉淀知识必须进入 proposed 状态
    - 人工确认后才能成为 active 知识
    """

    __tablename__ = "company_recruiting_knowledge_items"
    __table_args__ = (
        Index("ix_crk_org_type", "org_id", "knowledge_type"),
        Index("ix_crk_org_status", "org_id", "status"),
        Index("ix_crk_org_job_profile", "org_id", "job_profile_id"),
        Index("ix_crk_effective", "org_id", "effective_from", "effective_to"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    job_profile_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    knowledge_type: Mapped[KnowledgeItemType] = mapped_column(
        enum_column(KnowledgeItemType, "knowledge_item_type"), nullable=False, index=True
    )
    status: Mapped[KnowledgeItemStatus] = mapped_column(
        enum_column(KnowledgeItemStatus, "knowledge_item_status"),
        nullable=False,
        default=KnowledgeItemStatus.DRAFT,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(None, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    embedding_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
