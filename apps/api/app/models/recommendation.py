"""Recommendation — 主动推荐模型。

每次推荐表示一条"候选人与职位匹配"的推荐记录。
由后台定时任务自动生成，用户可在 Dashboard 上查看和操作。
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class RecommendationType(str, enum.Enum):
    CANDIDATE_JOB_MATCH = "candidate_job_match"
    NEW_CANDIDATE = "new_candidate"
    NEW_JOB = "new_job"


class Recommendation(Base):
    """推荐记录 — 由后台引擎自动生成。

    主动推荐的核心数据模型:
    - candidate_job_match: 候选人-职位匹配推荐（主要类型）
    - new_candidate: 新候选人入库提醒
    - new_job: 新职位发布提醒
    """

    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[RecommendationType] = mapped_column(
        SAEnum(RecommendationType, name="recommendation_type"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    candidate_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("candidates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("job_positions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    score: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="匹配评分 0-100",
    )
    reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="推荐理由",
    )
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
