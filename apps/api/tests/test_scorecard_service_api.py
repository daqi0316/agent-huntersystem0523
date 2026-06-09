from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.scorecards import router as scorecards_router
from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.schemas.scorecard import ScorecardTemplateCreate
from app.services.scorecard import ScorecardService


def _template_payload() -> dict:
    return {
        "name": "Java P7 技术面评分卡",
        "round_type": "technical",
        "status": "draft",
        "dimensions": [
            {
                "name": "技术深度",
                "weight": 0.6,
                "description": "能深入讲解 JVM 和分布式事务",
                "required": True,
                "anchors": [{"score": 5, "anchor_text": "能解释线上调优取舍"}],
            },
            {
                "name": "项目经验",
                "weight": 0.4,
                "description": "主导过中大型项目",
                "required": True,
                "anchors": [{"score": 3, "anchor_text": "能描述项目流程"}],
            },
        ],
    }


def _template_read() -> dict:
    now = datetime(2026, 6, 8, tzinfo=UTC)
    return {
        "id": "33333333-3333-3333-3333-333333333333",
        "job_profile_id": None,
        "profile_version_id": None,
        "name": "Java P7 技术面评分卡",
        "round_type": "technical",
        "status": "draft",
        "total_weight": 1.0,
        "created_by": "test-user-id",
        "created_at": now,
        "updated_at": now,
        "dimensions": [],
    }


class TestScorecardSchema:
    def test_rejects_dimension_weights_not_equal_one(self) -> None:
        payload = _template_payload()
        payload["dimensions"][0]["weight"] = 0.5

        with pytest.raises(ValueError) as exc:
            ScorecardTemplateCreate(**payload)

        assert "权重总和必须等于 1.0" in str(exc.value)


def _make_app(db_mock) -> FastAPI:
    app = FastAPI()
    app.include_router(scorecards_router, prefix="/scorecards")

    async def fake_get_db():
        yield db_mock

    async def fake_org_scoped_db():
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), db_mock

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[org_scoped_db] = fake_org_scoped_db
    return app


class TestScorecardApi:
    def test_list_templates(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.list_templates = AsyncMock(return_value=([_template_read()], 1))

        with patch("app.api.scorecards.ScorecardService", return_value=svc):
            resp = TestClient(app).get("/scorecards/templates")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        svc.list_templates.assert_awaited_once_with(
            skip=0,
            limit=20,
            job_profile_id=None,
            round_type=None,
            status=None,
        )

    def test_create_template(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        template = SimpleNamespace(id="33333333-3333-3333-3333-333333333333")
        svc.create_template = AsyncMock(return_value=template)
        svc.to_template_dict = AsyncMock(return_value=_template_read())

        with patch("app.api.scorecards.ScorecardService", return_value=svc):
            resp = TestClient(app).post("/scorecards/templates", json=_template_payload())

        assert resp.status_code == 201
        assert resp.json()["data"]["name"] == "Java P7 技术面评分卡"
        assert svc.create_template.await_args.kwargs["created_by"] == "test-user-id"

    def test_submit_interview_scorecard_not_found(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.submit_for_interview = AsyncMock(return_value=None)

        payload = {
            "scorecard_template_id": "33333333-3333-3333-3333-333333333333",
            "verdict": "consider",
            "dimension_scores": [
                {
                    "dimension_id": "44444444-4444-4444-4444-444444444444",
                    "score": 4,
                    "evidence": "能说明项目取舍",
                }
            ],
        }
        with patch("app.api.scorecards.ScorecardService", return_value=svc):
            resp = TestClient(app).post(
                "/scorecards/interviews/55555555-5555-5555-5555-555555555555/submissions",
                json=payload,
            )

        assert resp.status_code == 404
        assert "面试不存在" in resp.json()["error"]


class TestScorecardService:
    async def test_create_from_job_profile_returns_none_without_dimensions(self) -> None:
        db = AsyncMock()
        result = Mock()
        result.scalar_one_or_none.return_value = SimpleNamespace(id="profile-id", evaluation_dimensions=[])
        db.execute.return_value = result

        service = ScorecardService(db)
        got = await service.create_from_job_profile(
            profile_id="11111111-1111-1111-1111-111111111111",
            round_type="technical",
            name=None,
            status="draft",
            created_by="test-user-id",
        )

        assert got is None
