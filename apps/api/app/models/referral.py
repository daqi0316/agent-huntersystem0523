"""P6-3 + P6-4: self-serve trial + 老带新 referral model。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class ReferralCode(Base):
    __tablename__ = "referral_code"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    seat_reward: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class ReferralUse(Base):
    __tablename__ = "referral_use"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    referral_code_id: Mapped[str] = mapped_column(String(36), nullable=False)
    inviter_org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    new_org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    new_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    seat_rewarded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
