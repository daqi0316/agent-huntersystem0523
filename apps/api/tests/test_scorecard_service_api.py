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
from app.schemas.scorecard import ScorecardTemplateCreate, ScorecardDimensionScoreCreate, ScorecardTemplateUpdate
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
                "anchors": [
                    {"score": 1, "anchor_text": "无法解释核心技术原理"},
                    {"score": 3, "anchor_text": "能完成日常开发但原理不深"},
                    {"score": 5, "anchor_text": "能解释线上调优取舍"},
                ],
            },
            {
                "name": "项目经验",
                "weight": 0.4,
                "description": "主导过中大型项目",
                "required": True,
                "anchors": [
                    {"score": 1, "anchor_text": "项目描述模糊"},
                    {"score": 3, "anchor_text": "能描述项目流程"},
                    {"score": 5, "anchor_text": "能说明架构演进和个人决策"},
                ],
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

    def test_rejects_dimension_without_required_behavior_anchors(self) -> None:
        payload = _template_payload()
        payload["dimensions"][0]["anchors"] = [{"score": 5, "anchor_text": "只有高分锚定"}]

        with pytest.raises(ValueError) as exc:
            ScorecardTemplateCreate(**payload)

        assert "1/3/5 行为锚定" in str(exc.value)

    def test_rejects_low_score_without_confidence(self) -> None:
        with pytest.raises(ValueError) as exc:
            ScorecardDimensionScoreCreate(
                dimension_id="d1",
                score=2,
                evidence="表现不佳",
                confidence=None,
            )
        assert "confidence" in str(exc.value).lower()

    def test_rejects_high_score_without_confidence(self) -> None:
        with pytest.raises(ValueError) as exc:
            ScorecardDimensionScoreCreate(
                dimension_id="d1",
                score=5,
                evidence="表现极好",
                confidence=None,
            )
        assert "confidence" in str(exc.value).lower()

    def test_accepts_mid_score_without_confidence(self) -> None:
        s = ScorecardDimensionScoreCreate(
            dimension_id="d1",
            score=3,
            evidence="表现正常",
            confidence=None,
        )
        assert s.score == 3
        assert s.confidence is None


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

    def test_update_template(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.update_template = AsyncMock(return_value=SimpleNamespace(id="33333333-3333-3333-3333-333333333333"))
        svc.to_template_dict = AsyncMock(return_value=_template_read())

        with patch("app.api.scorecards.ScorecardService", return_value=svc):
            resp = TestClient(app).put(
                "/scorecards/templates/33333333-3333-3333-3333-333333333333",
                json={"name": "新名称"},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Java P7 技术面评分卡"

    def test_update_template_not_found(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.update_template = AsyncMock(return_value=None)

        with patch("app.api.scorecards.ScorecardService", return_value=svc):
            resp = TestClient(app).put(
                "/scorecards/templates/nonexistent",
                json={"name": "新名称"},
            )

        assert resp.status_code == 404
        assert "不存在" in resp.json()["error"]

    def test_update_template_validates_schema(self) -> None:
        app = _make_app(MagicMock())

        with patch("app.api.scorecards.ScorecardService"):
            # 空 body → schema 校验失败
            resp = TestClient(app).put(
                "/scorecards/templates/33333333-3333-3333-3333-333333333333",
                json={},
            )
        # FastAPI 的 Pydantic 校验会返回 422
        assert resp.status_code == 422

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

    def test_validate_behavior_anchors_rejects_missing_anchor_scores(self) -> None:
        payload = _template_payload()
        payload["dimensions"][1]["anchors"] = [
            {"score": 1, "anchor_text": "弱"},
            {"score": 3, "anchor_text": "中"},
        ]

        with pytest.raises(ValueError) as exc:
            ScorecardTemplateCreate(**payload)

        assert "1/3/5 行为锚定" in str(exc.value)

    async def test_update_template_draft_success(self) -> None:
        db = AsyncMock()
        template = SimpleNamespace(
            id="33333333-3333-3333-3333-333333333333",
            name="旧名称",
            round_type="technical",
            status="draft",
            total_weight=1.0,
            created_by="test-user-id",
        )
        svc = ScorecardService(db)

        # get_template 返回 draft 模板
        svc.get_template = AsyncMock(return_value=template)
        svc._dimensions_for_template = AsyncMock(return_value=[])
        svc.to_template_dict = AsyncMock(return_value={
            "id": template.id,
            "name": "新名称",
            "round_type": "technical",
            "status": "draft",
            "total_weight": 1.0,
        })

        from app.schemas.scorecard import ScorecardTemplateUpdate, ScorecardDimensionCreate, ScorecardAnchorCreate

        update = ScorecardTemplateUpdate(
            name="新名称",
            round_type="technical",
            dimensions=[
                ScorecardDimensionCreate(
                    name="沟通能力",
                    weight=0.5,
                    required=True,
                    anchors=[
                        ScorecardAnchorCreate(score=1, anchor_text="无法沟通"),
                        ScorecardAnchorCreate(score=3, anchor_text="能正常沟通"),
                        ScorecardAnchorCreate(score=5, anchor_text="沟通极佳"),
                    ],
                ),
                ScorecardDimensionCreate(
                    name="技术能力",
                    weight=0.5,
                    required=True,
                    anchors=[
                        ScorecardAnchorCreate(score=1, anchor_text="技术薄弱"),
                        ScorecardAnchorCreate(score=3, anchor_text="能完成任务"),
                        ScorecardAnchorCreate(score=5, anchor_text="技术卓越"),
                    ],
                ),
            ],
        )
        got = await svc.update_template(template.id, update, updated_by="test-user")
        assert got is not None
        assert got.name == "新名称"

    async def test_update_template_rejects_non_draft(self) -> None:
        db = AsyncMock()
        template = SimpleNamespace(id="t1", name="旧", round_type="technical", status="active")
        svc = ScorecardService(db)
        svc.get_template = AsyncMock(return_value=template)

        from app.schemas.scorecard import ScorecardTemplateUpdate

        with pytest.raises(ValueError, match="仅 draft"):
            await svc.update_template("t1", ScorecardTemplateUpdate(name="新"), updated_by="u")

    async def test_update_template_returns_none_for_missing(self) -> None:
        svc = ScorecardService(AsyncMock())
        svc.get_template = AsyncMock(return_value=None)

        from app.schemas.scorecard import ScorecardTemplateUpdate

        got = await svc.update_template("nonexistent", ScorecardTemplateUpdate(name="新"), updated_by="u")
        assert got is None

    async def test_update_template_rejects_missing_anchors(self) -> None:
        db = AsyncMock()
        template = SimpleNamespace(id="t1", name="旧", round_type="technical", status="draft")
        svc = ScorecardService(db)
        svc.get_template = AsyncMock(return_value=template)
        svc._dimensions_for_template = AsyncMock(return_value=[])

        from app.schemas.scorecard import ScorecardTemplateUpdate, ScorecardDimensionCreate, ScorecardAnchorCreate

        with pytest.raises(ValueError, match="1/3/5"):
            await svc.update_template(
                "t1",
                ScorecardTemplateUpdate(
                    dimensions=[
                        ScorecardDimensionCreate(
                            name="测试",
                            weight=1.0,
                            anchors=[ScorecardAnchorCreate(score=5, anchor_text="仅高分")],
                        )
                    ]
                ),
                updated_by="u",
            )

    async def test_template_allowed_for_interview_allows_explicit_template_when_no_profile_mapping_exists(self) -> None:
        db = AsyncMock()
        active_templates_result = Mock()
        active_templates_result.scalars.return_value.all.return_value = [
            SimpleNamespace(id="template-a", job_profile_id="profile-a"),
            SimpleNamespace(id="template-b", job_profile_id="profile-b"),
        ]
        job_result = Mock()
        job_result.scalar_one_or_none.return_value = SimpleNamespace(id="job-position-1", job_profile_id=None)
        db.execute.side_effect = [active_templates_result, job_result]

        service = ScorecardService(db)
        allowed = await service._template_allowed_for_interview(
            SimpleNamespace(job_profile_id="profile-a"),
            "22222222-2222-2222-2222-222222222222",
        )

        assert allowed is True

    async def test_template_allowed_for_interview_rejects_different_template_when_exact_match_exists(self) -> None:
        db = AsyncMock()
        exact_template = SimpleNamespace(id="template-exact", job_profile_id="profile-exact")
        selected_template = SimpleNamespace(id="template-selected", job_profile_id="profile-a")
        active_templates_result = Mock()
        active_templates_result.scalars.return_value.all.return_value = [selected_template, exact_template]
        job_result = Mock()
        job_result.scalar_one_or_none.return_value = SimpleNamespace(id="job-position-1", job_profile_id="profile-exact")
        db.execute.side_effect = [active_templates_result, job_result]

        service = ScorecardService(db)
        allowed = await service._template_allowed_for_interview(
            selected_template,
            "22222222-2222-2222-2222-222222222222",
        )

        assert allowed is False

    async def test_template_allowed_for_interview_accepts_single_active_template_compatibility(self) -> None:
        db = AsyncMock()
        active_template = SimpleNamespace(id="template-a", job_profile_id="profile-a")
        active_templates_result = Mock()
        active_templates_result.scalars.return_value.all.return_value = [active_template]
        job_result = Mock()
        job_result.scalar_one_or_none.return_value = SimpleNamespace(id="job-position-1", job_profile_id="profile-a")
        db.execute.side_effect = [active_templates_result, job_result]

        service = ScorecardService(db)
        allowed = await service._template_allowed_for_interview(
            active_template,
            "22222222-2222-2222-2222-222222222222",
        )

        assert allowed is True
