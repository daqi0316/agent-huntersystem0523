"""P5-3: 国内支付 — PaymentOrder + Subscription + Plan/Status enums。"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SAEnum,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class PaymentPlan(str, enum.Enum):
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    GRACE_PERIOD = "grace_period"


class PaymentChannel(str, enum.Enum):
    WECHAT = "wechat"
    ALIPAY = "alipay"


PLAN_PRICING_CENTS = {
    PaymentPlan.STARTER: 0,
    PaymentPlan.PRO: 29900,
    PaymentPlan.ENTERPRISE: 99900,
}

PLAN_QUOTAS = {
    PaymentPlan.STARTER: {"max_users": 10, "max_candidates": 1000, "llm_tokens_per_month": 500_000},
    PaymentPlan.PRO: {"max_users": 50, "max_candidates": 10000, "llm_tokens_per_month": 2_000_000},
    PaymentPlan.ENTERPRISE: {"max_users": 500, "max_candidates": 100000, "llm_tokens_per_month": 10_000_000},
}


class PaymentOrder(Base):
    __tablename__ = "payment_order"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    plan: Mapped[PaymentPlan] = mapped_column(
        SAEnum(PaymentPlan, name="payment_plan", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    billing_cycle: Mapped[str] = mapped_column(String(16), nullable=False, server_default="monthly")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="CNY")
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=PaymentStatus.PENDING,
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False, server_default="wechat")
    out_trade_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    prepay_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    refund_amount_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Subscription(Base):
    __tablename__ = "subscription"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    plan: Mapped[PaymentPlan] = mapped_column(
        SAEnum(PaymentPlan, name="payment_plan", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    billing_cycle: Mapped[str] = mapped_column(String(16), nullable=False, server_default="monthly")
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=SubscriptionStatus.ACTIVE,
    )
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    grace_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_payment_order_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
