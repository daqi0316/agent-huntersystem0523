"""面试官校准 schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CalibrationMetricComputeRequest(BaseModel):
    """计算面试官校准指标的请求参数。"""
    interviewer_id: str | None = Field(None, description="指定面试官，不传则计算所有")
    period_start: datetime | None = None
    period_end: datetime | None = None


class CalibrationMetricResponse(BaseModel):
    id: str
    interviewer_id: str
    period_start: datetime
    period_end: datetime
    sample_size: int = 0
    avg_score: float | None = None
    score_stddev: float | None = None
    severity_bias: float | None = None
    correlation_with_probation: float | None = None
    false_positive_rate: float | None = None
    false_negative_rate: float | None = None
    strict_rate: float | None = None
    lenient_rate: float | None = None
    pass_rate: float | None = None
    computed_at: datetime | None = None

    model_config = {"from_attributes": True}
