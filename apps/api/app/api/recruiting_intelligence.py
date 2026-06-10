"""P2-1: 招聘结果回流 API — 评分卡有效性 / 画像优化建议 / 结果特征。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.org_context import org_scoped_db
from app.core.response import error, ok_list, success
from app.schemas.recruiting_intelligence import (
    OutcomeFeatureBatchCreate,
    ProfileOptimizationSuggestionCreate,
    ProfileOptimizationSuggestionUpdate,
    RecruitingOutcomeFeatureCreate,
    ValidityMetricFilter,
)
from app.services.recruiting_intelligence import (
    OutcomeFeatureService,
    SuggestionService,
    ValidityMetricService,
)

router = APIRouter()
ORG_SCOPED_DEP = Depends(org_scoped_db)


# ── Scorecard Validity Metrics ────────────────────────────────────────


@router.post("/validity-metrics/compute")
async def compute_validity_metrics(
    template_id: str | None = Query(None),
    dimension_id: str | None = Query(None),
    interviewer_id: str | None = Query(None),
    min_sample_size: int = Query(0, ge=0),
    od=ORG_SCOPED_DEP,
):
    _, db = od
    filter_params = ValidityMetricFilter(
        scorecard_template_id=template_id,
        dimension_id=dimension_id,
        interviewer_id=interviewer_id,
        min_sample_size=min_sample_size,
    )
    try:
        metrics = await ValidityMetricService(db).compute_metrics(filter_params)
    except Exception as exc:
        return error(str(exc), status_code=500)
    return success([_metric_dict(m) for m in metrics])


@router.get("/validity-metrics")
async def list_validity_metrics(
    template_id: str | None = Query(None),
    dimension_id: str | None = Query(None),
    interviewer_id: str | None = Query(None),
    od=ORG_SCOPED_DEP,
):
    _, db = od
    filter_params = ValidityMetricFilter(
        scorecard_template_id=template_id,
        dimension_id=dimension_id,
        interviewer_id=interviewer_id,
    )
    metrics = await ValidityMetricService(db).get_metrics(filter_params)
    return success([_metric_dict(m) for m in metrics])


def _metric_dict(m) -> dict:
    return {
        "id": m.id,
        "scorecard_template_id": m.scorecard_template_id,
        "dimension_id": m.dimension_id,
        "interviewer_id": m.interviewer_id,
        "sample_size": m.sample_size,
        "correlation_with_probation": m.correlation_with_probation,
        "false_positive_rate": m.false_positive_rate,
        "false_negative_rate": m.false_negative_rate,
        "avg_score": m.avg_score,
        "actual_success_rate": m.actual_success_rate,
        "computed_at": m.computed_at.isoformat() if m.computed_at else None,
    }


# ── Profile Optimization Suggestions ─────────────────────────────────


@router.post("/optimization-suggestions", status_code=201)
async def create_suggestion(data: ProfileOptimizationSuggestionCreate, od=ORG_SCOPED_DEP):
    _, db = od
    try:
        suggestion = await SuggestionService(db).create(data)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    return success(_suggestion_dict(suggestion))


@router.get("/optimization-suggestions")
async def list_suggestions(
    job_profile_id: str | None = Query(None),
    status: str | None = Query(None),
    suggestion_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    od=ORG_SCOPED_DEP,
):
    _, db = od
    items, total = await SuggestionService(db).list(
        job_profile_id=job_profile_id,
        status=status,
        suggestion_type=suggestion_type,
        skip=skip,
        limit=limit,
    )
    return ok_list([_suggestion_dict(i) for i in items], total, skip, limit)


@router.get("/optimization-suggestions/{suggestion_id}")
async def get_suggestion(suggestion_id: str, od=ORG_SCOPED_DEP):
    _, db = od
    suggestion = await SuggestionService(db).get(suggestion_id)
    if suggestion is None:
        return error("建议不存在", status_code=404)
    return success(_suggestion_dict(suggestion))


@router.put("/optimization-suggestions/{suggestion_id}")
async def update_suggestion(suggestion_id: str, data: ProfileOptimizationSuggestionUpdate, od=ORG_SCOPED_DEP):
    _, db = od
    try:
        suggestion = await SuggestionService(db).update(suggestion_id, data)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    if suggestion is None:
        return error("建议不存在", status_code=404)
    return success(_suggestion_dict(suggestion))


@router.delete("/optimization-suggestions/{suggestion_id}")
async def delete_suggestion(suggestion_id: str, od=ORG_SCOPED_DEP):
    _, db = od
    deleted = await SuggestionService(db).delete(suggestion_id)
    if not deleted:
        return error("建议不存在", status_code=404)
    return success(True)


def _suggestion_dict(s) -> dict:
    return {
        "id": s.id,
        "job_profile_id": s.job_profile_id,
        "profile_version_id": s.profile_version_id,
        "suggestion_type": s.suggestion_type.value if hasattr(s.suggestion_type, "value") else s.suggestion_type,
        "target_field": s.target_field,
        "current_value": s.current_value,
        "suggested_value": s.suggested_value,
        "evidence_summary": s.evidence_summary,
        "confidence": s.confidence,
        "status": s.status.value if hasattr(s.status, "value") else s.status,
        "reviewed_by": s.reviewed_by,
        "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
        "review_notes": s.review_notes,
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


# ── Recruiting Outcome Features ──────────────────────────────────────


@router.post("/outcome-features", status_code=201)
async def create_outcome_feature(data: RecruitingOutcomeFeatureCreate, od=ORG_SCOPED_DEP):
    _, db = od
    try:
        feature = await OutcomeFeatureService(db).create(data)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    return success(_feature_dict(feature))


@router.post("/outcome-features/batch", status_code=201)
async def batch_create_outcome_features(data: OutcomeFeatureBatchCreate, od=ORG_SCOPED_DEP):
    _, db = od
    try:
        features = await OutcomeFeatureService(db).batch_create(data)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    return success([_feature_dict(f) for f in features])


@router.get("/outcome-features")
async def list_outcome_features(
    candidate_id: str | None = Query(None),
    feature_name: str | None = Query(None),
    outcome_label: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    od=ORG_SCOPED_DEP,
):
    _, db = od
    items, total = await OutcomeFeatureService(db).list(
        candidate_id=candidate_id,
        feature_name=feature_name,
        outcome_label=outcome_label,
        skip=skip,
        limit=limit,
    )
    return ok_list([_feature_dict(i) for i in items], total, skip, limit)


@router.delete("/outcome-features/by-candidate/{candidate_id}")
async def delete_outcome_features_by_candidate(candidate_id: str, od=ORG_SCOPED_DEP):
    _, db = od
    count = await OutcomeFeatureService(db).delete_by_candidate(candidate_id)
    return success({"deleted": count})


def _feature_dict(f) -> dict:
    return {
        "id": f.id,
        "candidate_id": f.candidate_id,
        "application_id": f.application_id,
        "onboarding_id": f.onboarding_id,
        "feature_name": f.feature_name,
        "feature_value": f.feature_value,
        "source": f.source,
        "outcome_label": f.outcome_label,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
