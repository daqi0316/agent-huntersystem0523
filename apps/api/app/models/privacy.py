"""P5-4: PIPL 个保法 — DataExportRequest + DataDeleteRequest + enums。"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, DateTime, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DataExportStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class DataDeleteStatus(str, enum.Enum):
    PENDING = "pending"
    SOFT_DELETED = "soft_deleted"
    GRACE_PERIOD = "grace_period"
    HARD_DELETED = "hard_deleted"
    CANCELLED = "cancelled"


GRACE_PERIOD_DAYS = 30
EXPORT_RETENTION_DAYS = 7
EXPORT_DOWNLOAD_BASE = "/api/v1/privacy/export"


class DataExportRequest(Base):
    __tablename__ = "data_export_request"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[DataExportStatus] = mapped_column(
        SAEnum(DataExportStatus, name="data_export_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=DataExportStatus.PENDING,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    row_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")


class DataDeleteRequest(Base):
    __tablename__ = "data_delete_request"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[DataDeleteStatus] = mapped_column(
        SAEnum(DataDeleteStatus, name="data_delete_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=DataDeleteStatus.PENDING,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_hard_delete_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    placeholder_uuid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
