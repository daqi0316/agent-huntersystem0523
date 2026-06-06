"""P5-9: 法务协议接受记录 — ToS / PP / DPA versioned acceptance。

客户在注册时必须接受 ToS 与 PP, DPA 按需 (跨境/企业客户自动要求)。
每次协议版本更新需用户重新接受。
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum as SAEnum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AgreementType(str, enum.Enum):
    TERMS_OF_SERVICE = "terms_of_service"
    PRIVACY_POLICY = "privacy_policy"
    DATA_PROCESSING_AGREEMENT = "data_processing_agreement"


CURRENT_VERSIONS = {
    AgreementType.TERMS_OF_SERVICE: "v1.0",
    AgreementType.PRIVACY_POLICY: "v1.0",
    AgreementType.DATA_PROCESSING_AGREEMENT: "v1.0",
}


class LegalAcceptance(Base):
    __tablename__ = "legal_acceptance"
    __table_args__ = (
        Index("ix_legal_acceptance_user_type_version", "user_id", "agreement_type", "version", unique=True),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agreement_type: Mapped[AgreementType] = mapped_column(
        SAEnum(AgreementType, name="agreement_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
