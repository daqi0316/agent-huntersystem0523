import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import TSVECTOR, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class SessionSummary(Base):
    __tablename__ = "session_summaries"

    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_session_summaries_user_session"),
        Index("ix_session_summaries_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_insights: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="结构化洞察: preferred_skills, salary_range, screening_patterns, rejected_reasons 等",
    )
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        nullable=True,
        comment="全文搜索向量 (由 trigger 自动从 summary 更新)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
