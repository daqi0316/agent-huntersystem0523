"""WeChatOAuthState — 微信扫码登录 state 临时存储。

P5-2: 防 CSRF + 防 state 重放 (state 用后 mark used_at, 不可再用)。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class WeChatOAuthState(Base):
    __tablename__ = "wechat_oauth_state"
    __table_args__ = ({"extend_existing": True},)

    state: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: secrets_token())
    redirect_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def secrets_token() -> str:
    import secrets
    return secrets.token_urlsafe(32)
