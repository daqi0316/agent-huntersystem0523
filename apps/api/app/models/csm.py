"""P6-12: CSM churn 监控 — csm_task 表 + 自动检测 + 飞书 + 1-on-1 任务。

7d 未登录 OR 健康度 < 30 → 自动建 CSM 任务 + 飞书通知。
cron daily 跑, 复用 P5-15 健康度 + P5-7 告警升级路径。
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CSMTaskType(str, enum.Enum):
    CHURN_RISK = "churn_risk"
    LOW_HEALTH = "low_health"
    TRIAL_EXPIRING = "trial_expiring"
    USAGE_DROP = "usage_drop"
    PAYMENT_FAILED = "payment_failed"


class CSMTaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    DISMISSED = "dismissed"


class CSMTaskSeverity(str, enum.Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


CHURN_DAYS_NO_LOGIN = 7
LOW_HEALTH_THRESHOLD = 30


class CSMTask(Base):
    __tablename__ = "csm_task"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    type: Mapped[CSMTaskType] = mapped_column(
        SAEnum(CSMTaskType, name="csm_task_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    severity: Mapped[CSMTaskSeverity] = mapped_column(
        SAEnum(CSMTaskSeverity, name="csm_task_severity", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=CSMTaskSeverity.P2,
    )
    status: Mapped[CSMTaskStatus] = mapped_column(
        SAEnum(CSMTaskStatus, name="csm_task_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=CSMTaskStatus.PENDING,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(
        __import__("sqlalchemy").JSON, nullable=False, default=dict, server_default="{}",
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
