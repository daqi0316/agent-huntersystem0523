"""P5-10: AI 监管合规 tests (override + appeal + SLA + audit)。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.ai_compliance import router
    _app.include_router(router, prefix="/api/v1/ai-compliance")
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


class TestAuditEnum:
    def test_ai_override_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.AI_OVERRIDE.value == "ai_score_override"

    def test_appeal_filed_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.APPEAL_FILED.value == "appeal_filed"

    def test_appeal_resolved_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.APPEAL_RESOLVED.value == "appeal_resolved"


class TestAppealSLA:
    def test_sla_7_days(self):
        from app.models.appeal import APPEAL_SLA_DAYS
        assert APPEAL_SLA_DAYS == 7


class TestAppealStatus:
    def test_five_statuses(self):
        from app.models.appeal import AppealStatus
        assert len(AppealStatus) == 5

    def test_pending_state(self):
        from app.models.appeal import AppealStatus
        assert AppealStatus.PENDING.value == "pending"

    def test_resolved_accepted_state(self):
        from app.models.appeal import AppealStatus
        assert AppealStatus.RESOLVED_ACCEPTED.value == "resolved_accepted"

    def test_resolved_rejected_state(self):
        from app.models.appeal import AppealStatus
        assert AppealStatus.RESOLVED_REJECTED.value == "resolved_rejected"


class TestRecommendationAISource:
    def test_ai_score_source_field_exists(self):
        from app.models.recommendation import Recommendation
        cols = [c.name for c in Recommendation.__table__.columns]
        assert "ai_score_source" in cols
        assert "score_overridden" in cols
        assert "score_overridden_by" in cols
        assert "score_overridden_at" in cols
        assert "score_override_reason" in cols

    def test_interview_evaluation_ai_source(self):
        from app.models.interview_evaluation import InterviewEvaluation
        cols = [c.name for c in InterviewEvaluation.__table__.columns]
        assert "ai_score_source" in cols
        assert "score_overridden" in cols


class TestAISourceEndpoint:
    def test_get_ai_source_404(self, client, override_db, mock_db):
        from sqlalchemy import select as sa_select
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=result_mock)

        resp = client.get("/api/v1/ai-compliance/recommendations/non-existent/ai-source")
        assert resp.status_code == 404

    def test_get_ai_source_returns(self, client, override_db, mock_db):
        from app.models.recommendation import Recommendation

        reco = MagicMock()
        reco.id = "reco-1"
        reco.score = 85
        reco.score_overridden = False
        reco.ai_score_source = {
            "llm": "qwen3.6",
            "model_version": "v1",
            "prompt_hash": "abc123",
            "generated_at": "2026-06-01T00:00:00Z",
        }

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=reco)
        mock_db.execute = AsyncMock(return_value=result_mock)

        resp = client.get("/api/v1/ai-compliance/recommendations/reco-1/ai-source")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["score"] == 85
        assert data["ai_source"]["llm"] == "qwen3.6"


class TestOverrideScore:
    def test_invalid_score_too_high(self, client, override_db, mock_db):
        resp = client.post(
            "/api/v1/ai-compliance/recommendations/reco-1/override-score",
            json={"new_score": 150, "reason": "test"},
        )
        assert resp.status_code == 422

    def test_invalid_score_negative(self, client, override_db, mock_db):
        resp = client.post(
            "/api/v1/ai-compliance/recommendations/reco-1/override-score",
            json={"new_score": -1, "reason": "test"},
        )
        assert resp.status_code == 422

    def test_short_reason(self, client, override_db, mock_db):
        resp = client.post(
            "/api/v1/ai-compliance/recommendations/reco-1/override-score",
            json={"new_score": 80, "reason": "x"},
        )
        assert resp.status_code == 422


class TestAppealCreation:
    def test_invalid_target_type(self, client, override_db, mock_db):
        resp = client.post(
            "/api/v1/ai-compliance/appeals",
            json={"target_type": "invalid", "target_id": "x", "reason": "this is a valid reason"},
        )
        assert resp.status_code == 400

    def test_short_reason(self, client, override_db, mock_db):
        resp = client.post(
            "/api/v1/ai-compliance/appeals",
            json={"target_type": "recommendation", "target_id": "x", "reason": "short"},
        )
        assert resp.status_code == 422


class TestAIDisclosureDoc:
    def test_doc_exists(self):
        from pathlib import Path
        path = Path("/Users/qixia/agent-huntersystem0523/docs/ai-disclosure.md")
        assert path.exists(), "ai-disclosure.md must exist"
        content = path.read_text()
        assert "AI" in content
        assert "来源" in content or "标识" in content
