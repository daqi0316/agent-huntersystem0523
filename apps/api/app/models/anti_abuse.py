"""P5-11: 反垃圾 model — SmsVerification + DeviceFingerprint。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class SmsPurpose:
    REGISTER = "register"
    LOGIN = "login"
    RESET_PASSWORD = "reset_password"
    BIND_PHONE = "bind_phone"


SMS_CODE_LENGTH = 6
SMS_CODE_TTL_MINUTES = 5
SMS_MAX_ATTEMPTS = 5


class SmsVerification(Base):
    __tablename__ = "sms_verification"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, server_default="register")
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeviceFingerprint(Base):
    __tablename__ = "device_fingerprint"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    invite_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
