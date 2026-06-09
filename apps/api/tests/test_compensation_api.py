from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.compensation import router as compensation_router
from app.core.org_context import OrgContext, org_scoped_db
from app.models.compensation import OfferNegotiationStatus


def _make_app(db_mock) -> FastAPI:
    app = FastAPI()
    app.include_router(compensation_router)

    async def fake_org_scoped_db():
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), db_mock

    app.dependency_overrides[org_scoped_db] = fake_org_scoped_db
    return app


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.first.return_value = items[0] if items else None
    result.scalars.return_value = scalars
    return result


def _benchmark():
    now = datetime(2026, 6, 8, tzinfo=UTC)
    return SimpleNamespace(
        id="b1",
        industry="互联网",
        city="上海",
        job_family="engineering",
        job_title="Java 高级工程师",
        level="P7",
        company_type="互联网大厂",
        company_name="BenchmarkCo",
        base_min=500000,
        base_p50=650000,
        base_max=800000,
        total_min=700000,
        total_p50=900000,
        total_max=1100000,
        currency="CNY",
        period="year",
        data_source="internal",
        confidence=0.8,
        sample_size=20,
        effective_date=date(2026, 6, 1),
        created_at=now,
        updated_at=now,
    )


def _expectation():
    now = datetime(2026, 6, 8, tzinfo=UTC)
    return SimpleNamespace(
        id="e1",
        candidate_id="c1",
        current_base=600000,
        current_total=800000,
        expected_base=750000,
        expected_total=1200000,
        minimum_acceptable=1000000,
        notice_period="1个月",
        competing_offers=[{"company": "X", "total": 1150000}],
        notes="有竞品 offer",
        created_at=now,
        updated_at=now,
    )


def _offer(status=OfferNegotiationStatus.NEGOTIATING, accepted=None, reject_reason=None):
    now = datetime(2026, 6, 8, tzinfo=UTC)
    return SimpleNamespace(
        id="o1",
        candidate_id="c1",
        application_id="a1",
        job_id="j1",
        expected_total=1200000,
        first_offer_total=950000,
        final_offer_total=1000000,
        market_p50=900000,
        budget_min=800000,
        budget_max=1000000,
        negotiation_status=status,
        accepted=accepted,
        reject_reason=reject_reason,
        notes="谈判中",
        created_at=now,
        updated_at=now,
    )


class TestCompensationApi:
    def test_list_benchmarks_filters(self) -> None:
        db = AsyncMock()
        db.execute.return_value = _scalars_result([_benchmark()])
        resp = TestClient(_make_app(db)).get(
            "/compensation/benchmarks",
            params={"city": "上海", "level": "P7", "job_title": "Java", "job_family": "engineering"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["city"] == "上海"
        assert data["items"][0]["total_p50"] == 900000

    def test_create_benchmark(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        payload = {
            "city": "上海",
            "job_family": "engineering",
            "job_title": "Java 高级工程师",
            "level": "P7",
            "total_p50": 900000,
        }
        with patch("app.api.compensation.CompensationBenchmark", return_value=_benchmark()):
            resp = TestClient(_make_app(db)).post("/compensation/benchmarks", json=payload)

        assert resp.status_code == 201
        assert resp.json()["data"]["job_title"] == "Java 高级工程师"
        db.add.assert_called_once()

    def test_compare_high_risk(self) -> None:
        db = AsyncMock()
        resp = TestClient(_make_app(db)).get(
            "/compensation/compare",
            params={"expected_total": 1200000, "market_p50": 900000, "budget_min": 800000, "budget_max": 1000000},
        )

        data = resp.json()["data"]
        assert data["risk_label"] == "high"
        assert data["gap_to_budget_max_pct"] == 20.0
        assert "候选人期望超过预算上限" in data["reasons"]

    def test_create_candidate_expectation_not_found(self) -> None:
        db = AsyncMock()
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=None)
        with patch("app.api.compensation.CandidateService", return_value=service):
            resp = TestClient(_make_app(db)).post(
                "/candidates/c-missing/compensation-expectation",
                json={"expected_total": 1000000},
            )

        assert resp.status_code == 404

    def test_create_candidate_expectation(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=SimpleNamespace(id="c1"))
        with patch("app.api.compensation.CandidateService", return_value=service), patch(
            "app.api.compensation.CandidateCompensationExpectation", return_value=_expectation()
        ):
            resp = TestClient(_make_app(db)).post(
                "/candidates/c1/compensation-expectation",
                json={"expected_total": 1200000, "minimum_acceptable": 1000000, "notice_period": "1个月"},
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["expected_total"] == 1200000

    def test_candidate_compensation(self) -> None:
        db = AsyncMock()
        db.execute.side_effect = [_scalars_result([_expectation()]), _scalars_result([_offer()])]
        resp = TestClient(_make_app(db)).get("/candidates/c1/compensation")

        data = resp.json()["data"]
        assert data["expectations"][0]["expected_total"] == 1200000
        assert data["offers"][0]["budget_max"] == 1000000
        assert data["risk"]["risk_label"] == "high"

    def test_create_offer_negotiation_record_invalid_status(self) -> None:
        db = AsyncMock()
        resp = TestClient(_make_app(db)).post(
            "/offers/o1/negotiation-records",
            json={"candidate_id": "c1", "negotiation_status": "bad"},
        )

        assert resp.status_code == 400

    def test_create_offer_negotiation_record(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        with patch("app.api.compensation.OfferNegotiationRecord", return_value=_offer()):
            resp = TestClient(_make_app(db)).post(
                "/offers/o1/negotiation-records",
                json={
                    "candidate_id": "c1",
                    "application_id": "a1",
                    "job_id": "j1",
                    "expected_total": 1200000,
                    "market_p50": 900000,
                    "budget_min": 800000,
                    "budget_max": 1000000,
                    "negotiation_status": "negotiating",
                },
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["risk"]["risk_label"] == "high"

    def test_salary_loss_analytics(self) -> None:
        db = AsyncMock()
        db.execute.return_value = _scalars_result([
            _offer(status=OfferNegotiationStatus.REJECTED, accepted=False, reject_reason="薪资不匹配"),
            _offer(status=OfferNegotiationStatus.REJECTED, accepted=False, reject_reason="地点不匹配"),
        ])
        resp = TestClient(_make_app(db)).get("/compensation/analytics/salary-loss")

        data = resp.json()["data"]
        assert data["total_rejected"] == 2
        assert data["salary_rejected"] == 1
        assert data["salary_rejection_ratio"] == 50.0
