"""P5 in-app notification (P6-5 D1) — 站内信表 + 列表/未读/已读 endpoint。

替代邮件: 用户站内信 + (微信模板, P6-5 D2 阻塞) + 短信 (P6-5 D3)。
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class NotificationType(str, enum.Enum):
    INVITE_RECEIVED = "invite_received"
    TRIAL_EXPIRING = "trial_expiring"
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAILED = "payment_failed"
    APPEAL_FILED = "appeal_filed"
    APPEAL_RESOLVED = "appeal_resolved"
    ONBOARDING_DAY1 = "onboarding_day1"
    ONBOARDING_DAY3 = "onboarding_day3"
    ONBOARDING_DAY7 = "onboarding_day7"
    ONBOARDING_DAY14 = "onboarding_day14"
    CHURN_RISK = "churn_risk"
    SYSTEM = "system"


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
