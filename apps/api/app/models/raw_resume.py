"""v0.4d: Raw resume 表 — 存原始简历文本，让 LLM 解析失败可重试。

设计动机：
  resume_parser._handle_parse_resume 之前是 file → LLM extract →
  create_candidate 一步走。LLM 失败时 raw_text 丢失，候选人也不会被
  创建，用户需要重新上传整个文件。

  v0.4d 事务边界：先落 raw_text 到 raw_resume 表（status=processing），
  再调 LLM。LLM 成功 → create_candidate + 链 candidate_id + status=parsed。
  LLM 失败 → status=failed + error_message 落库，raw_text 保留供后续
  retry 工具重新解析（retry 工具推 v0.4d+ 后续 PR，本 PR 只加事务边界）。
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._base import enum_column


class RawResumeStatus(str, enum.Enum):
    PROCESSING = "processing"
    PARSED = "parsed"
    FAILED = "failed"


class RawResume(Base):
    __tablename__ = "raw_resumes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_job_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    status: Mapped[RawResumeStatus] = mapped_column(
        enum_column(RawResumeStatus, "raw_resume_status"),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def new_raw_resume_id() -> str:
    """Generate new raw_resume id (UUID v4 string format)."""
    return str(uuid.uuid4())
