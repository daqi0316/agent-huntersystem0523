import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    HR = "hr"
    RECRUITER = "recruiter"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        default=UserRole.HR,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    wechat_unionid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wechat_openid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wechat_nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wechat_avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="email"
    )
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    phone_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    phone_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
