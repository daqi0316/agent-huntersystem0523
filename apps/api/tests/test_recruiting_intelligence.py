"""P2-1: 招聘结果回流 — ScorecardValidityMetric / ProfileOptimizationSuggestion / RecruitingOutcomeFeature 测试。"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.recruiting_intelligence import router as ri_router
from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.models.recruiting_intelligence import SuggestionStatus, SuggestionType
from app.services.recruiting_intelligence import (
    OutcomeFeatureService,
    SuggestionService,
    ValidityMetricService,
)


# ─── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    _app = FastAPI()
    _app.include_router(ri_router, prefix="/recruiting-intelligence")
    return _app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _patch_db(app: FastAPI, db_mock: AsyncMock):
    async def fake_get_db():
        yield db_mock

    async def fake_org_scoped_db():
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), db_mock

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[org_scoped_db] = fake_org_scoped_db


def _metric_dict(
    id: str = "m1",
    template_id: str = "t1",
    dimension_id: str = "d1",
    interviewer_id: str = "iv1",
    sample_size: int = 10,
    correlation: float | None = 0.75,
    fpr: float | None = 0.1,
    fnr: float | None = 0.2,
    avg: float = 3.5,
    success_rate: float = 0.8,
) -> dict:
    return {
        "id": id,
        "scorecard_template_id": template_id,
        "dimension_id": dimension_id,
        "interviewer_id": interviewer_id,
        "sample_size": sample_size,
        "correlation_with_probation": correlation,
        "false_positive_rate": fpr,
        "false_negative_rate": fnr,
        "avg_score": avg,
        "actual_success_rate": success_rate,
        "computed_at": "2026-06-08T12:00:00+00:00",
    }


def _make_metric(**kw):
    """返回 SimpleNamespace 模拟 ORM model."""
    base = _metric_dict(**{k: v for k, v in kw.items() if k != "computed_at"})
    ns = SimpleNamespace(**base)
    ns.computed_at = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    return ns


def _suggestion_dict(
    id: str = "s1",
    job_profile_id: str = "jp1",
    status: str = "proposed",
    suggestion_type: str = "weight_change",
) -> dict:
    return {
        "id": id,
        "job_profile_id": job_profile_id,
        "profile_version_id": None,
        "suggestion_type": suggestion_type,
        "target_field": "technical_skill",
        "current_value": "0.5",
        "suggested_value": "0.6",
        "evidence_summary": "该维度与试用期通过率强相关",
        "confidence": 0.85,
        "status": status,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_notes": None,
        "created_by": "test-user-id",
        "created_at": "2026-06-08T12:00:00+00:00",
        "updated_at": "2026-06-08T12:00:00+00:00",
    }


def _make_suggestion(**kw):
    base = _suggestion_dict(**{k: v for k, v in kw.items() if k not in ("created_at", "updated_at")})
    ns = SimpleNamespace(**base)
    # 直接用字符串，不套 SimpleNamespace(value=lambda:)
    # _suggestion_dict 通过 hasattr(..., "value") 做 fallback 兼容 enum/str
    ns.suggestion_type = base["suggestion_type"]
    ns.status = base["status"]
    ns.created_at = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    ns.updated_at = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    ns.reviewed_at = None
    return ns


def _feature_dict(
    id: str = "f1",
    candidate_id: str = "c1",
    feature_name: str = "tech_score",
    source: str = "interview",
    outcome_label: str = "probation_passed",
) -> dict:
    return {
        "id": id,
        "candidate_id": candidate_id,
        "application_id": None,
        "onboarding_id": None,
        "feature_name": feature_name,
        "feature_value": "85",
        "source": source,
        "outcome_label": outcome_label,
        "created_at": "2026-06-08T12:00:00+00:00",
    }


def _make_feature(**kw):
    base = _feature_dict(**{k: v for k, v in kw.items() if k != "created_at"})
    ns = SimpleNamespace(**base)
    ns.created_at = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    return ns


# ====================================================================
#  API tests — ScorecardValidityMetric
# ====================================================================


class TestValidityMetricApi:
    def test_compute_metrics_success(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.compute_metrics = AsyncMock(return_value=[_make_metric()])

        with patch("app.api.recruiting_intelligence.ValidityMetricService", return_value=svc):
            resp = TestClient(app).post("/recruiting-intelligence/validity-metrics/compute")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["sample_size"] == 10
        assert data[0]["correlation_with_probation"] == 0.75

    def test_compute_metrics_with_filters(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.compute_metrics = AsyncMock(return_value=[_make_metric()])

        with patch("app.api.recruiting_intelligence.ValidityMetricService", return_value=svc):
            resp = TestClient(app).post(
                "/recruiting-intelligence/validity-metrics/compute?template_id=t1&dimension_id=d1&min_sample_size=5"
            )

        assert resp.status_code == 200
        svc.compute_metrics.assert_awaited_once()
        filter_arg = svc.compute_metrics.call_args[0][0]
        assert filter_arg.scorecard_template_id == "t1"
        assert filter_arg.dimension_id == "d1"
        assert filter_arg.min_sample_size == 5

    def test_compute_metrics_error_returns_500(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.compute_metrics = AsyncMock(side_effect=ValueError("DB connection failed"))

        with patch("app.api.recruiting_intelligence.ValidityMetricService", return_value=svc):
            resp = TestClient(app).post("/recruiting-intelligence/validity-metrics/compute")

        assert resp.status_code == 500
        assert "DB connection failed" in resp.json()["error"]

    def test_list_validity_metrics(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.get_metrics = AsyncMock(return_value=[_make_metric(id="m1"), _make_metric(id="m2")])

        with patch("app.api.recruiting_intelligence.ValidityMetricService", return_value=svc):
            resp = TestClient(app).get("/recruiting-intelligence/validity-metrics?template_id=t1")

        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2
        svc.get_metrics.assert_awaited_once()
        filter_arg = svc.get_metrics.call_args[0][0]
        assert filter_arg.scorecard_template_id == "t1"

    def test_list_validity_metrics_empty(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.get_metrics = AsyncMock(return_value=[])

        with patch("app.api.recruiting_intelligence.ValidityMetricService", return_value=svc):
            resp = TestClient(app).get("/recruiting-intelligence/validity-metrics")

        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ====================================================================
#  API tests — ProfileOptimizationSuggestion
# ====================================================================


_suggestion_create_payload = {
    "job_profile_id": "jp1",
    "suggestion_type": "weight_change",
    "target_field": "technical_skill",
    "current_value": "0.5",
    "suggested_value": "0.6",
    "evidence_summary": "强相关",
    "confidence": 0.85,
    "created_by": "test-user-id",
}


class TestSuggestionApi:
    def test_create_suggestion(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.create = AsyncMock(return_value=_make_suggestion())

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).post(
                "/recruiting-intelligence/optimization-suggestions",
                json=_suggestion_create_payload,
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["status"] == "proposed"

    def test_create_suggestion_validation_error(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.create = AsyncMock(side_effect=ValueError("invalid type"))

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).post(
                "/recruiting-intelligence/optimization-suggestions",
                json=_suggestion_create_payload,
            )

        assert resp.status_code == 400

    def test_create_suggestion_schema_invalid_type(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        payload = dict(_suggestion_create_payload, suggestion_type="invalid_type")

        with patch("app.api.recruiting_intelligence.SuggestionService"):
            resp = TestClient(app).post(
                "/recruiting-intelligence/optimization-suggestions",
                json=payload,
            )

        # Pydantic pattern validation rejects invalid type
        assert resp.status_code == 422

    def test_list_suggestions(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.list = AsyncMock(return_value=([_make_suggestion(), _make_suggestion(id="s2")], 2))

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).get("/recruiting-intelligence/optimization-suggestions")

        assert resp.status_code == 200
        assert resp.json()["total"] == 2
        assert len(resp.json()["data"]) == 2

    def test_list_suggestions_with_filters(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.list = AsyncMock(return_value=([_make_suggestion()], 1))

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).get(
                "/recruiting-intelligence/optimization-suggestions?job_profile_id=jp1"
                "&status=proposed&suggestion_type=weight_change&skip=0&limit=10"
            )

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        svc.list.assert_awaited_once_with(
            job_profile_id="jp1",
            status="proposed",
            suggestion_type="weight_change",
            skip=0,
            limit=10,
        )

    def test_get_suggestion(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.get = AsyncMock(return_value=_make_suggestion())

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).get("/recruiting-intelligence/optimization-suggestions/s1")

        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "s1"

    def test_get_suggestion_not_found(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.get = AsyncMock(return_value=None)

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).get("/recruiting-intelligence/optimization-suggestions/nonexistent")

        assert resp.status_code == 404
        assert "不存在" in resp.json()["error"]

    def test_update_suggestion(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.update = AsyncMock(return_value=_make_suggestion(status="accepted"))

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).put(
                "/recruiting-intelligence/optimization-suggestions/s1",
                json={"status": "accepted", "reviewed_by": "reviewer-1", "review_notes": "同意"},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "accepted"

    def test_update_suggestion_not_found(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.update = AsyncMock(return_value=None)

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).put(
                "/recruiting-intelligence/optimization-suggestions/nonexistent",
                json={"status": "accepted", "reviewed_by": "reviewer-1"},
            )

        assert resp.status_code == 404
        assert "不存在" in resp.json()["error"]

    def test_update_suggestion_invalid_status(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)

        with patch("app.api.recruiting_intelligence.SuggestionService"):
            resp = TestClient(app).put(
                "/recruiting-intelligence/optimization-suggestions/s1",
                json={"status": "invalid_status"},
            )

        assert resp.status_code == 422

    def test_update_suggestion_value_error(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.update = AsyncMock(side_effect=ValueError("invalid transition"))

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).put(
                "/recruiting-intelligence/optimization-suggestions/s1",
                json={"status": "accepted", "reviewed_by": "reviewer-1"},
            )

        assert resp.status_code == 400

    def test_delete_suggestion(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.delete = AsyncMock(return_value=True)

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).delete("/recruiting-intelligence/optimization-suggestions/s1")

        assert resp.status_code == 200
        assert resp.json()["data"] is True

    def test_delete_suggestion_not_found(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.delete = AsyncMock(return_value=False)

        with patch("app.api.recruiting_intelligence.SuggestionService", return_value=svc):
            resp = TestClient(app).delete("/recruiting-intelligence/optimization-suggestions/nonexistent")

        assert resp.status_code == 404
        assert "不存在" in resp.json()["error"]


# ====================================================================
#  API tests — RecruitingOutcomeFeature
# ====================================================================


_feature_create_payload = {
    "candidate_id": "c1",
    "feature_name": "tech_score",
    "feature_value": "85",
    "source": "interview",
    "outcome_label": "probation_passed",
}


class TestOutcomeFeatureApi:
    def test_create_feature(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.create = AsyncMock(return_value=_make_feature())

        with patch("app.api.recruiting_intelligence.OutcomeFeatureService", return_value=svc):
            resp = TestClient(app).post(
                "/recruiting-intelligence/outcome-features",
                json=_feature_create_payload,
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["feature_name"] == "tech_score"

    def test_create_feature_value_error(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.create = AsyncMock(side_effect=ValueError("invalid"))

        with patch("app.api.recruiting_intelligence.OutcomeFeatureService", return_value=svc):
            resp = TestClient(app).post(
                "/recruiting-intelligence/outcome-features",
                json=_feature_create_payload,
            )

        assert resp.status_code == 400

    def test_batch_create_features(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.batch_create = AsyncMock(return_value=[_make_feature(), _make_feature(id="f2")])

        payload = {
            "features": [
                {**_feature_create_payload, "candidate_id": "c1"},
                {**_feature_create_payload, "candidate_id": "c1", "feature_name": "comm_score"},
            ]
        }

        with patch("app.api.recruiting_intelligence.OutcomeFeatureService", return_value=svc):
            resp = TestClient(app).post(
                "/recruiting-intelligence/outcome-features/batch",
                json=payload,
            )

        assert resp.status_code == 201
        assert len(resp.json()["data"]) == 2

    def test_batch_create_empty_rejected(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)

        with patch("app.api.recruiting_intelligence.OutcomeFeatureService"):
            resp = TestClient(app).post(
                "/recruiting-intelligence/outcome-features/batch",
                json={"features": []},
            )

        # Pydantic min_length validation
        assert resp.status_code == 422

    def test_list_features(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.list = AsyncMock(return_value=([_make_feature(), _make_feature(id="f2")], 2))

        with patch("app.api.recruiting_intelligence.OutcomeFeatureService", return_value=svc):
            resp = TestClient(app).get("/recruiting-intelligence/outcome-features")

        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_features_with_filters(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.list = AsyncMock(return_value=([_make_feature()], 1))

        with patch("app.api.recruiting_intelligence.OutcomeFeatureService", return_value=svc):
            resp = TestClient(app).get(
                "/recruiting-intelligence/outcome-features?candidate_id=c1"
                "&feature_name=tech_score&outcome_label=probation_passed"
            )

        assert resp.status_code == 200
        svc.list.assert_awaited_once_with(
            candidate_id="c1",
            feature_name="tech_score",
            outcome_label="probation_passed",
            skip=0,
            limit=100,
        )

    def test_delete_features_by_candidate(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.delete_by_candidate = AsyncMock(return_value=3)

        with patch("app.api.recruiting_intelligence.OutcomeFeatureService", return_value=svc):
            resp = TestClient(app).delete("/recruiting-intelligence/outcome-features/by-candidate/c1")

        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] == 3

    def test_delete_features_by_candidate_zero(self, app: FastAPI) -> None:
        db = AsyncMock()
        _patch_db(app, db)
        svc = MagicMock()
        svc.delete_by_candidate = AsyncMock(return_value=0)

        with patch("app.api.recruiting_intelligence.OutcomeFeatureService", return_value=svc):
            resp = TestClient(app).delete("/recruiting-intelligence/outcome-features/by-candidate/c1")

        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] == 0


# ====================================================================
#  Service tests — ValidityMetricService
# ====================================================================


class TestValidityMetricService:
    def test_pearson_correlation_perfect_positive(self) -> None:
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [1.0, 2.0, 3.0, 4.0, 5.0]
        r = ValidityMetricService._pearson_correlation(x, y)
        assert r is not None
        assert abs(r - 1.0) < 1e-9

    def test_pearson_correlation_perfect_negative(self) -> None:
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [5.0, 4.0, 3.0, 2.0, 1.0]
        r = ValidityMetricService._pearson_correlation(x, y)
        assert r is not None
        assert abs(r - (-1.0)) < 1e-9

    def test_pearson_correlation_zero(self) -> None:
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [3.0, 3.0, 3.0, 3.0, 3.0]  # no variance
        r = ValidityMetricService._pearson_correlation(x, y)
        assert r is None  # zero denominator

    def test_pearson_correlation_insufficient_data(self) -> None:
        r = ValidityMetricService._pearson_correlation([1.0], [1.0])
        assert r is None

    def test_pearson_correlation_no_variance_in_x(self) -> None:
        x = [3.0, 3.0, 3.0]
        y = [1.0, 2.0, 3.0]
        r = ValidityMetricService._pearson_correlation(x, y)
        assert r is None

    def test_pearson_correlation_clamps_float_error(self) -> None:
        """浮点误差不应使相关系数超出 [-1, 1]."""
        x = [1.0, 2.0]
        y = [1.0000001, 1.9999999]
        r = ValidityMetricService._pearson_correlation(x, y)
        assert r is not None
        assert -1.0 <= r <= 1.0

    def test_group_and_compute_basic(self) -> None:
        svc = ValidityMetricService(MagicMock())
        rows = [
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 5.0, "status": "probation_passed", "candidate_id": "c1"},
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 4.0, "status": "probation_passed", "candidate_id": "c2"},
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 2.0, "status": "probation_failed", "candidate_id": "c3"},
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 1.0, "status": "probation_failed", "candidate_id": "c4"},
        ]
        results = svc._group_and_compute(rows)
        assert len(results) == 1
        r = results[0]
        assert r["sample_size"] == 4
        assert r["actual_success_rate"] == 0.5
        assert r["avg_score"] == 3.0
        # High scorers (>=4): 2, passed: 2 → false_negative_rate = 0 / 2 = 0.0
        assert r["false_negative_rate"] == 0.0
        # Low scorers (<=2): 2, passed: 0 → false_positive_rate = 0 / 2 = 0.0
        assert r["false_positive_rate"] == 0.0

    def test_group_and_compute_with_misclassifications(self) -> None:
        svc = ValidityMetricService(MagicMock())
        rows = [
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 5.0, "status": "probation_failed", "candidate_id": "c1"},  # FN: high score but failed
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 4.0, "status": "probation_passed", "candidate_id": "c2"},
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 2.0, "status": "probation_passed", "candidate_id": "c3"},  # FP: low score but passed
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 1.0, "status": "probation_failed", "candidate_id": "c4"},
        ]
        results = svc._group_and_compute(rows)
        assert len(results) == 1
        r = results[0]
        # FN: high scorers (>=4) = 2, failed = 1 → 1/2 = 0.5
        assert r["false_negative_rate"] == 0.5
        # FP: low scorers (<=2) = 2, passed = 1 → 1/2 = 0.5
        assert r["false_positive_rate"] == 0.5

    def test_group_and_compute_skips_single_sample(self) -> None:
        svc = ValidityMetricService(MagicMock())
        rows = [
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 5.0, "status": "probation_passed", "candidate_id": "c1"},
        ]
        results = svc._group_and_compute(rows)
        assert results == []

    def test_group_and_compute_no_high_or_low_scorers(self) -> None:
        """中间分 (3) 不应产生误判率分母. 所有分数都是 3 -> 没有高分/低分者 -> FPR/FNR = None."""
        svc = ValidityMetricService(MagicMock())
        rows = [
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 3.0, "status": "probation_passed", "candidate_id": "c1"},
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 3.0, "status": "probation_failed", "candidate_id": "c2"},
        ]
        results = svc._group_and_compute(rows)
        assert len(results) == 1
        r = results[0]
        assert r["sample_size"] == 2
        assert r["false_positive_rate"] is None
        assert r["false_negative_rate"] is None

    def test_group_and_compute_multiple_groups(self) -> None:
        svc = ValidityMetricService(MagicMock())
        rows = [
            # group 1: (t1, d1, iv1) — 2 samples
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 4.0, "status": "probation_passed", "candidate_id": "c1"},
            {"scorecard_template_id": "t1", "dimension_id": "d1", "interviewer_id": "iv1",
             "score": 3.0, "status": "probation_failed", "candidate_id": "c2"},
            # group 2: (t1, d2, iv1) — 2 samples
            {"scorecard_template_id": "t1", "dimension_id": "d2", "interviewer_id": "iv1",
             "score": 5.0, "status": "probation_passed", "candidate_id": "c1"},
            {"scorecard_template_id": "t1", "dimension_id": "d2", "interviewer_id": "iv1",
             "score": 2.0, "status": "probation_failed", "candidate_id": "c4"},
            # group 3: (t2, d1, iv2) — 2 samples
            {"scorecard_template_id": "t2", "dimension_id": "d1", "interviewer_id": "iv2",
             "score": 2.0, "status": "probation_failed", "candidate_id": "c3"},
            {"scorecard_template_id": "t2", "dimension_id": "d1", "interviewer_id": "iv2",
             "score": 4.0, "status": "probation_passed", "candidate_id": "c5"},
        ]
        results = svc._group_and_compute(rows)
        assert len(results) == 3  # three distinct groups, each >= 2 samples


# ====================================================================
#  Service tests — SuggestionService
# ====================================================================


class TestSuggestionService:
    async def test_create_suggestion(self) -> None:
        db = AsyncMock()

        svc = SuggestionService(db)
        data = MagicMock()
        data.job_profile_id = "jp1"
        data.profile_version_id = None
        data.suggestion_type = "weight_change"
        data.target_field = "tech"
        data.current_value = "0.5"
        data.suggested_value = "0.6"
        data.evidence_summary = "evidence"
        data.confidence = 0.85
        data.created_by = "user1"

        suggestion = await svc.create(data)
        assert suggestion is not None
        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()

    async def test_get_suggestion_valid_uuid(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = _make_suggestion()
        db.execute.return_value = result_mock

        svc = SuggestionService(db)
        got = await svc.get("00000000-0000-0000-0000-000000000001")
        assert got is not None
        assert got.id == "s1"

    async def test_get_suggestion_invalid_uuid(self) -> None:
        db = AsyncMock()
        svc = SuggestionService(db)
        got = await svc.get("not-a-uuid")
        assert got is None
        db.execute.assert_not_called()

    async def test_get_suggestion_not_found(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        svc = SuggestionService(db)
        got = await svc.get("00000000-0000-0000-0000-000000000001")
        assert got is None

    async def test_update_suggestion_status(self) -> None:
        db = AsyncMock()
        suggestion = _make_suggestion(id="s1")
        svc = SuggestionService(db)
        svc.get = AsyncMock(return_value=suggestion)

        data = MagicMock()
        data.status = "accepted"
        data.reviewed_by = "reviewer-1"
        data.review_notes = "good"

        updated = await svc.update("s1", data)
        assert updated is not None
        assert suggestion.status == SuggestionStatus.ACCEPTED  # mutated in place

    async def test_update_suggestion_not_found(self) -> None:
        db = AsyncMock()
        svc = SuggestionService(db)
        svc.get = AsyncMock(return_value=None)

        data = MagicMock()
        data.status = "accepted"
        data.reviewed_by = "reviewer-1"
        data.review_notes = None

        got = await svc.update("nonexistent", data)
        assert got is None

    async def test_update_marks_reviewed_at_on_terminal(self) -> None:
        db = AsyncMock()
        suggestion = _make_suggestion(id="s1", status="proposed")
        svc = SuggestionService(db)
        svc.get = AsyncMock(return_value=suggestion)

        data = MagicMock()
        data.status = "rejected"
        data.reviewed_by = "reviewer-1"
        data.review_notes = "not needed"

        await svc.update("s1", data)
        assert suggestion.reviewed_at is not None

    async def test_delete_suggestion(self) -> None:
        db = AsyncMock()
        suggestion = _make_suggestion(id="s1")
        svc = SuggestionService(db)
        svc.get = AsyncMock(return_value=suggestion)

        deleted = await svc.delete("s1")
        assert deleted is True
        db.delete.assert_called_once_with(suggestion)
        db.commit.assert_awaited_once()

    async def test_delete_suggestion_not_found(self) -> None:
        db = AsyncMock()
        svc = SuggestionService(db)
        svc.get = AsyncMock(return_value=None)

        deleted = await svc.delete("nonexistent")
        assert deleted is False
        db.delete.assert_not_called()

    async def test_list_with_filters(self) -> None:
        db = AsyncMock()

        # mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        # mock list query
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [
            _make_suggestion(id="s1"),
            _make_suggestion(id="s2"),
        ]

        db.execute = AsyncMock(side_effect=[count_result, list_result])

        svc = SuggestionService(db)
        items, total = await svc.list(
            job_profile_id="jp1",
            status="proposed",
            suggestion_type="weight_change",
        )
        assert total == 2
        assert len(items) == 2

    async def test_list_empty(self) -> None:
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_result, list_result])

        svc = SuggestionService(db)
        items, total = await svc.list()
        assert total == 0
        assert items == []


# ====================================================================
#  Service tests — OutcomeFeatureService
# ====================================================================


class TestOutcomeFeatureService:
    async def test_create_feature(self) -> None:
        db = AsyncMock()

        svc = OutcomeFeatureService(db)
        data = MagicMock()
        data.candidate_id = "c1"
        data.application_id = None
        data.onboarding_id = None
        data.feature_name = "tech_score"
        data.feature_value = "85"
        data.source = "interview"
        data.outcome_label = "probation_passed"

        feature = await svc.create(data)
        assert feature is not None
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    async def test_batch_create(self) -> None:
        db = AsyncMock()

        svc = OutcomeFeatureService(db)
        item1 = MagicMock(candidate_id="c1", application_id=None, onboarding_id=None,
                          feature_name="tech", feature_value="85", source="interview",
                          outcome_label="passed")
        item2 = MagicMock(candidate_id="c1", application_id=None, onboarding_id=None,
                          feature_name="comm", feature_value="70", source="interview",
                          outcome_label="passed")

        data = MagicMock()
        data.features = [item1, item2]

        features = await svc.batch_create(data)
        assert len(features) == 2
        assert db.add.call_count == 2
        assert db.commit.await_count == 1

    async def test_list_with_filters(self) -> None:
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [_make_feature()]
        db.execute = AsyncMock(side_effect=[count_result, list_result])

        svc = OutcomeFeatureService(db)
        items, total = await svc.list(candidate_id="c1", feature_name="tech", outcome_label="passed")
        assert total == 1
        assert len(items) == 1

    async def test_list_no_filters(self) -> None:
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 3
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [
            _make_feature(id="f1"), _make_feature(id="f2"), _make_feature(id="f3"),
        ]
        db.execute = AsyncMock(side_effect=[count_result, list_result])

        svc = OutcomeFeatureService(db)
        items, total = await svc.list()
        assert total == 3
        assert len(items) == 3

    async def test_delete_by_candidate(self) -> None:
        db = AsyncMock()
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [
            _make_feature(id="f1"),
            _make_feature(id="f2"),
        ]
        db.execute = AsyncMock(return_value=select_result)

        svc = OutcomeFeatureService(db)
        count = await svc.delete_by_candidate("c1")
        assert count == 2
        assert db.delete.call_count == 2
        db.commit.assert_awaited_once()

    async def test_delete_by_candidate_no_features(self) -> None:
        db = AsyncMock()
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=select_result)

        svc = OutcomeFeatureService(db)
        count = await svc.delete_by_candidate("c1")
        assert count == 0
        db.delete.assert_not_called()
        db.commit.assert_awaited_once()
