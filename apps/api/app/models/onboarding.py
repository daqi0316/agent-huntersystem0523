"""P5-15: 客户 onboarding runbook model — BatchImportRequest + CustomerHealthScore。"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, JSON, DateTime, Enum as SAEnum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class BatchImportStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


VALID_RISK_LEVELS = ("healthy", "at_risk", "high_risk", "unknown")


class RiskLevel(str, enum.Enum):
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    HIGH_RISK = "high_risk"
    UNKNOWN = "unknown"


RISK_THRESHOLDS = {
    "high_risk": (0, 50),
    "at_risk": (50, 70),
    "healthy": (70, 100),
}


class BatchImportRequest(Base):
    __tablename__ = "batch_import_request"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[BatchImportStatus] = mapped_column(
        SAEnum(BatchImportStatus, name="batch_import_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=BatchImportStatus.PENDING,
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class CustomerHealthScore(Base):
    __tablename__ = "customer_health_score"
    __table_args__ = (
        CheckConstraint(
            "login_score BETWEEN 0 AND 100 "
            "AND feature_score BETWEEN 0 AND 100 "
            "AND support_score BETWEEN 0 AND 100 "
            "AND referral_score BETWEEN 0 AND 100 "
            "AND total_score BETWEEN 0 AND 100",
            name="chk_health_score_range",
        ),
        CheckConstraint(
            "risk_level IN ('healthy', 'at_risk', 'high_risk', 'unknown')",
            name="chk_health_risk_level",
        ),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    login_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    feature_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    support_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    referral_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    total_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unknown")
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
