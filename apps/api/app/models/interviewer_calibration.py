"""Interviewer Calibration — 面试官评分校准指标。

度量每个面试官的评分偏差、区分度和误判率，用于：
- 识别过于宽松/严格的面试官
- 发现评分分歧度高的维度
- 反哺面试官培训
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class InterviewerCalibrationMetric(Base):
    """面试官校准指标（按时间段聚合）。

    核心指标说明：
    - severity_bias: 相对偏差。正值 = 该面试官比同期其他人给分高（偏宽松），负值 = 偏严格。
    - score_stddev: 评分标准差。反映面试官区分能力，过小说明给分集中在某个区间（无区分度）。
    """

    __tablename__ = "interviewer_calibration_metrics"
    __table_args__ = (
        Index("ix_calibration_interviewer", "interviewer_id"),
        Index("ix_calibration_period", "period_start", "period_end"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    interviewer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_stddev: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity_bias: Mapped[float | None] = mapped_column(Float, nullable=True)
    correlation_with_probation: Mapped[float | None] = mapped_column(Float, nullable=True)
    false_positive_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    false_negative_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    strict_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    lenient_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
