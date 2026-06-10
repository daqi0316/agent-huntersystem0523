"""RedFlagRule — 可版本化的红旗规则定义。

替代现有散落在各模型的 JSON red_flags 字段，
提供结构化、可引用的红旗规则主数据。
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class RedFlagSeverity(str, enum.Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class RedFlagScope(str, enum.Enum):
    REQUIREMENT = "requirement"        # 关联到画像要求项
    DIMENSION = "dimension"            # 关联到面试维度
    SCORE_THRESHOLD = "score_threshold"  # 分数阈值
    TENURE = "tenure"                  # 工作年限/稳定性
    KEYWORD = "keyword"                # 关键词匹配
    PATTERN = "pattern"                # 模式匹配


class RedFlagRule(Base):
    """红旗规则。

    用于定义在招聘流程中哪些情况应当触发红旗标记。
    支持关联到岗位画像、面试维度或独立使用。
    """

    __tablename__ = "red_flag_rules"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_profile_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[RedFlagScope] = mapped_column(
        enum_column(RedFlagScope, "red_flag_scope"), nullable=False, index=True
    )
    severity: Mapped[RedFlagSeverity] = mapped_column(
        enum_column(RedFlagSeverity, "red_flag_severity"), nullable=False, default=RedFlagSeverity.WARNING
    )
    condition_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
