"""P6-8 企微 OAuth state 表 (wecom 即 微信企业号, 与 wechat 个人版区分)。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class WecomOAuthState(Base):
    __tablename__ = "wecom_oauth_state"
    __table_args__ = (
        Index("ix_wecom_oauth_state_expires_at", "expires_at"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    state: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    redirect_uri: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
