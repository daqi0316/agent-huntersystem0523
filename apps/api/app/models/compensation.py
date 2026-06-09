from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models._base import enum_column


class OfferNegotiationStatus(str, enum.Enum):
    DRAFT = "draft"
    NEGOTIATING = "negotiating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class CompensationBenchmark(Base):
    __tablename__ = "compensation_benchmarks"
    __table_args__ = (
        Index("ix_comp_benchmarks_lookup", "city", "job_family", "job_title", "level"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    city: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    job_family: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    company_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="CNY", server_default="CNY")
    period: Mapped[str] = mapped_column(String(32), nullable=False, default="year", server_default="year")
    data_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CandidateCompensationExpectation(Base):
    __tablename__ = "candidate_compensation_expectations"
    __table_args__ = (Index("ix_candidate_comp_expect_candidate", "candidate_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    current_base: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_base: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    minimum_acceptable: Mapped[float | None] = mapped_column(Float, nullable=True)
    notice_period: Mapped[str | None] = mapped_column(String(128), nullable=True)
    competing_offers: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class OfferNegotiationRecord(Base):
    __tablename__ = "offer_negotiation_records"
    __table_args__ = (Index("ix_offer_negotiation_candidate_created", "candidate_id", "created_at"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("job_positions.id", ondelete="SET NULL"), nullable=True, index=True)
    expected_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_offer_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_offer_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    negotiation_status: Mapped[OfferNegotiationStatus] = mapped_column(
        enum_column(OfferNegotiationStatus, "offer_negotiation_status"), nullable=False, default=OfferNegotiationStatus.DRAFT, index=True
    )
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
