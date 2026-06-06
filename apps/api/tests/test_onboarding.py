"""P5-15: onboarding runbook tests (CSV 导入 + 健康度算法 + 4 维度权重)。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.onboarding import router
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def override_db(app, mock_db):
    from app.core.database import get_db
    from app.core.org_context import OrgContext, org_scoped_db

    async def _mock_get_db():
        yield mock_db

    async def _mock_org_scoped_db():
        org_ctx = OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr")
        yield org_ctx, mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[org_scoped_db] = _mock_org_scoped_db
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(org_scoped_db, None)


class TestCSVTemplates:
    def test_candidate_template(self, client, override_db, mock_db):
        resp = client.get("/onboarding/csv-template/candidate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "name" in data["required_columns"]
        assert "email" in data["required_columns"]
        assert "name" in data["template"]

    def test_job_template(self, client, override_db, mock_db):
        resp = client.get("/onboarding/csv-template/job_position")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "title" in data["required_columns"]

    def test_unknown_entity_400(self, client, override_db, mock_db):
        resp = client.get("/onboarding/csv-template/unknown")
        assert resp.status_code == 400


class TestCandidateImport:
    def test_import_valid_csv(self, client, override_db, mock_db):
        from app.models.onboarding import BatchImportRequest, BatchImportStatus
        from unittest.mock import patch

        batch = MagicMock()
        batch.id = "batch-1"
        batch.status = BatchImportStatus.COMPLETED

        with patch("app.api.onboarding.import_candidates_csv", new=AsyncMock(return_value=(
            batch,
            type("R", (), {"total": 2, "imported": 2, "failed": 0, "errors": []})(),
        ))):
            resp = client.post(
                "/onboarding/import/candidates",
                files={"file": ("test.csv", "name,email\n张三,zhang@x.com\n李四,li@x.com\n", "text/csv")},
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["imported"] == 2
        assert data["failed"] == 0


class TestHealthScore:
    def test_classify_risk_high(self):
        from app.services.onboarding import _classify_risk
        assert _classify_risk(30) == "high_risk"

    def test_classify_risk_at(self):
        from app.services.onboarding import _classify_risk
        assert _classify_risk(60) == "at_risk"

    def test_classify_risk_healthy(self):
        from app.services.onboarding import _classify_risk
        assert _classify_risk(85) == "healthy"

    def test_classify_risk_unknown(self):
        from app.services.onboarding import _classify_risk
        assert _classify_risk(-1) == "unknown"

    def test_risk_thresholds(self):
        from app.models.onboarding import RISK_THRESHOLDS
        assert RISK_THRESHOLDS["healthy"] == (70, 100)
        assert RISK_THRESHOLDS["at_risk"] == (50, 70)
        assert RISK_THRESHOLDS["high_risk"] == (0, 50)

    def test_health_score_endpoint(self, client, override_db, mock_db):
        from app.models.onboarding import CustomerHealthScore

        score = MagicMock()
        score.org_id = "o1"
        score.total_score = 75.0
        score.risk_level = "healthy"
        score.login_score = 80.0
        score.feature_score = 60.0
        score.support_score = 80.0
        score.referral_score = 60.0
        score.metrics_snapshot = {"active_users_7d": 5}
        score.computed_at = datetime.now(timezone.utc)

        with patch("app.api.onboarding.get_health_score", new=AsyncMock(return_value=score)):
            resp = client.get("/onboarding/health-score")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_score"] == 75.0
        assert data["risk_level"] == "healthy"
        assert "breakdown" in data


class TestImportResult:
    def test_required_candidate_cols(self):
        from app.services.onboarding import REQUIRED_CANDIDATE_COLS
        assert "name" in REQUIRED_CANDIDATE_COLS
        assert "email" in REQUIRED_CANDIDATE_COLS

    def test_required_job_cols(self):
        from app.services.onboarding import REQUIRED_JOB_COLS
        assert "title" in REQUIRED_JOB_COLS
