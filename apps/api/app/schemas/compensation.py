from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class CompensationBenchmarkCreate(BaseModel):
    industry: str | None = None
    city: str
    job_family: str
    job_title: str
    level: str
    company_type: str | None = None
    company_name: str | None = None
    base_min: float | None = None
    base_p50: float | None = None
    base_max: float | None = None
    total_min: float | None = None
    total_p50: float | None = None
    total_max: float | None = None
    currency: str = "CNY"
    period: str = "year"
    data_source: str | None = None
    confidence: float | None = None
    sample_size: int | None = None
    effective_date: date | None = None


class CompensationBenchmarkRead(CompensationBenchmarkCreate):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompensationExpectationCreate(BaseModel):
    current_base: float | None = None
    current_total: float | None = None
    expected_base: float | None = None
    expected_total: float | None = None
    minimum_acceptable: float | None = None
    notice_period: str | None = None
    competing_offers: list = Field(default_factory=list)
    notes: str | None = None


class CompensationExpectationRead(CompensationExpectationCreate):
    id: str
    candidate_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OfferNegotiationRecordCreate(BaseModel):
    candidate_id: str
    application_id: str | None = None
    job_id: str | None = None
    expected_total: float | None = None
    first_offer_total: float | None = None
    final_offer_total: float | None = None
    market_p50: float | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    negotiation_status: str = "draft"
    accepted: bool | None = None
    reject_reason: str | None = None
    notes: str | None = None


class OfferNegotiationRecordRead(OfferNegotiationRecordCreate):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompensationCompareRead(BaseModel):
    risk_label: str
    risk_score: int
    expected_total: float | None = None
    market_p50: float | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    gap_to_market_p50_pct: float | None = None
    gap_to_budget_max_pct: float | None = None
    reasons: list[str]
