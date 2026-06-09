from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.org_context import org_scoped_db
from app.core.response import error, success
from app.models.compensation import (
    CandidateCompensationExpectation,
    CompensationBenchmark,
    OfferNegotiationRecord,
    OfferNegotiationStatus,
)
from app.schemas.compensation import (
    CompensationBenchmarkCreate,
    CompensationCompareRead,
    CompensationExpectationCreate,
    OfferNegotiationRecordCreate,
)
from app.services.candidate import CandidateService

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _coerce_status(value: str):
    try:
        return OfferNegotiationStatus(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in OfferNegotiationStatus)
        raise ValueError(f"negotiation_status 必须是: {allowed}") from exc


def _benchmark_to_dict(item: CompensationBenchmark) -> dict:
    return {
        "id": item.id,
        "industry": item.industry,
        "city": item.city,
        "job_family": item.job_family,
        "job_title": item.job_title,
        "level": item.level,
        "company_type": item.company_type,
        "company_name": item.company_name,
        "base_min": item.base_min,
        "base_p50": item.base_p50,
        "base_max": item.base_max,
        "total_min": item.total_min,
        "total_p50": item.total_p50,
        "total_max": item.total_max,
        "currency": item.currency,
        "period": item.period,
        "data_source": item.data_source,
        "confidence": item.confidence,
        "sample_size": item.sample_size,
        "effective_date": item.effective_date,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _expectation_to_dict(item: CandidateCompensationExpectation) -> dict:
    return {
        "id": item.id,
        "candidate_id": item.candidate_id,
        "current_base": item.current_base,
        "current_total": item.current_total,
        "expected_base": item.expected_base,
        "expected_total": item.expected_total,
        "minimum_acceptable": item.minimum_acceptable,
        "notice_period": item.notice_period,
        "competing_offers": item.competing_offers or [],
        "notes": item.notes,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _offer_to_dict(item: OfferNegotiationRecord) -> dict:
    return {
        "id": item.id,
        "candidate_id": item.candidate_id,
        "application_id": item.application_id,
        "job_id": item.job_id,
        "expected_total": item.expected_total,
        "first_offer_total": item.first_offer_total,
        "final_offer_total": item.final_offer_total,
        "market_p50": item.market_p50,
        "budget_min": item.budget_min,
        "budget_max": item.budget_max,
        "negotiation_status": _enum_value(item.negotiation_status),
        "accepted": item.accepted,
        "reject_reason": item.reject_reason,
        "notes": item.notes,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _risk(expected_total: float | None, market_p50: float | None, budget_min: float | None, budget_max: float | None) -> CompensationCompareRead:
    reasons: list[str] = []
    risk_score = 0
    gap_market = None
    gap_budget = None
    if expected_total is not None and market_p50:
        gap_market = round((expected_total - market_p50) / market_p50 * 100, 1)
        if gap_market > 20:
            risk_score += 35
            reasons.append("候选人期望高于市场 P50 超过 20%")
        elif gap_market > 10:
            risk_score += 20
            reasons.append("候选人期望高于市场 P50 超过 10%")
    if expected_total is not None and budget_max:
        gap_budget = round((expected_total - budget_max) / budget_max * 100, 1)
        if expected_total > budget_max:
            risk_score += 45
            reasons.append("候选人期望超过预算上限")
        elif budget_min and expected_total < budget_min:
            risk_score += 10
            reasons.append("候选人期望低于预算下限，需校准职级或范围")
    if not reasons:
        reasons.append("薪酬期望处于可谈判区间")
    label = "low"
    if risk_score >= 60:
        label = "high"
    elif risk_score >= 25:
        label = "medium"
    return CompensationCompareRead(
        risk_label=label,
        risk_score=min(risk_score, 100),
        expected_total=expected_total,
        market_p50=market_p50,
        budget_min=budget_min,
        budget_max=budget_max,
        gap_to_market_p50_pct=gap_market,
        gap_to_budget_max_pct=gap_budget,
        reasons=reasons,
    )


@router.get("/compensation/benchmarks")
async def list_benchmarks(city: str | None = None, level: str | None = None, job_title: str | None = None, job_family: str | None = None, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    stmt = select(CompensationBenchmark).order_by(CompensationBenchmark.effective_date.desc().nullslast())
    if city:
        stmt = stmt.where(CompensationBenchmark.city == city)
    if level:
        stmt = stmt.where(CompensationBenchmark.level == level)
    if job_title:
        stmt = stmt.where(CompensationBenchmark.job_title.ilike(f"%{job_title}%"))
    if job_family:
        stmt = stmt.where(CompensationBenchmark.job_family == job_family)
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return success({"items": [_benchmark_to_dict(item) for item in items], "total": len(items)})


@router.post("/compensation/benchmarks", status_code=201)
async def create_benchmark(data: CompensationBenchmarkCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    item = CompensationBenchmark(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return success(_benchmark_to_dict(item))


@router.get("/compensation/compare")
async def compare_compensation(expected_total: float | None = None, market_p50: float | None = None, budget_min: float | None = None, budget_max: float | None = None, candidate_id: str | None = None, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    if candidate_id and expected_total is None:
        result = await db.execute(
            select(CandidateCompensationExpectation)
            .where(CandidateCompensationExpectation.candidate_id == candidate_id)
            .order_by(CandidateCompensationExpectation.created_at.desc())
        )
        expectation = result.scalars().first()
        if expectation:
            expected_total = expectation.expected_total
    return success(_risk(expected_total, market_p50, budget_min, budget_max).model_dump())


@router.post("/candidates/{candidate_id}/compensation-expectation", status_code=201)
async def create_candidate_expectation(candidate_id: str, data: CompensationExpectationCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    service = CandidateService(db)
    candidate = await service.get_by_id(candidate_id)
    if not candidate:
        return error("候选人不存在", status_code=404)
    item = CandidateCompensationExpectation(candidate_id=candidate_id, **data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return success(_expectation_to_dict(item))


@router.get("/candidates/{candidate_id}/compensation")
async def candidate_compensation(candidate_id: str, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    expectations_result = await db.execute(
        select(CandidateCompensationExpectation)
        .where(CandidateCompensationExpectation.candidate_id == candidate_id)
        .order_by(CandidateCompensationExpectation.created_at.desc())
    )
    offers_result = await db.execute(
        select(OfferNegotiationRecord)
        .where(OfferNegotiationRecord.candidate_id == candidate_id)
        .order_by(OfferNegotiationRecord.created_at.desc())
    )
    expectations = list(expectations_result.scalars().all())
    offers = list(offers_result.scalars().all())
    latest_expectation = expectations[0] if expectations else None
    latest_offer = offers[0] if offers else None
    risk = _risk(
        latest_expectation.expected_total if latest_expectation else None,
        latest_offer.market_p50 if latest_offer else None,
        latest_offer.budget_min if latest_offer else None,
        latest_offer.budget_max if latest_offer else None,
    )
    return success({
        "expectations": [_expectation_to_dict(item) for item in expectations],
        "offers": [_offer_to_dict(item) for item in offers],
        "risk": risk.model_dump(),
    })


@router.post("/offers/{offer_id}/negotiation-records", status_code=201)
async def create_offer_negotiation_record(offer_id: str, data: OfferNegotiationRecordCreate, od=ORG_SCOPED_DEP):
    org_ctx, db = od
    try:
        status = _coerce_status(data.negotiation_status)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    payload = data.model_dump()
    payload["negotiation_status"] = status
    item = OfferNegotiationRecord(**payload)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return success({**_offer_to_dict(item), "offer_id": offer_id, "risk": _risk(item.expected_total, item.market_p50, item.budget_min, item.budget_max).model_dump()})


@router.get("/compensation/analytics/salary-loss")
async def salary_loss_analytics(od=ORG_SCOPED_DEP):
    org_ctx, db = od
    result = await db.execute(select(OfferNegotiationRecord))
    records = list(result.scalars().all())
    rejected = [item for item in records if item.accepted is False or item.negotiation_status == OfferNegotiationStatus.REJECTED]
    salary_rejected = [item for item in rejected if item.reject_reason and "薪" in item.reject_reason]
    ratio = round(len(salary_rejected) / len(rejected) * 100, 1) if rejected else 0
    return success({"total_rejected": len(rejected), "salary_rejected": len(salary_rejected), "salary_rejection_ratio": ratio})
