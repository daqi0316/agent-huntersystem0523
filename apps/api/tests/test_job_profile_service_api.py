from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.job_profiles import router as job_profiles_router
from app.core.database import get_db
from app.core.org_context import OrgContext, org_scoped_db
from app.models.job_profile import JobProfile
from app.schemas.job_profile import JobProfileCreate
from app.services.job_profile import JobProfileService


def _valid_payload(code: str = "Java_P7") -> dict:
    return {
        "code": code,
        "title": "高级 Java 工程师",
        "level": "P7",
        "department": "技术部-后端架构组",
        "hard_requirements": ["5年以上 Java 开发经验"],
        "soft_requirements": ["跨团队协作"],
        "evaluation_dimensions": [
            {
                "dimension": "技术深度",
                "weight": 0.6,
                "must_have": "能深入讲解 JVM 和分布式事务",
                "key_questions": ["JVM 调优"],
                "scoring_guide": [{"score": 5, "evidence": "能解释线上调优取舍"}],
                "red_flags": ["只能描述 CRUD"],
            },
            {
                "dimension": "项目经验",
                "weight": 0.4,
                "must_have": "主导过中大型项目",
                "key_questions": ["团队分工"],
                "scoring_guide": [{"score": 3, "evidence": "能描述项目流程"}],
                "red_flags": [],
            },
        ],
        "salary_band": {
            "base_min": 40000,
            "base_max": 50000,
            "total_min": 600000,
            "total_max": 800000,
            "currency": "CNY",
            "period": "monthly",
        },
        "interview_focus": ["验证主导程度"],
        "is_active": True,
    }


def _read_payload(code: str = "Java_P7") -> dict:
    payload = _valid_payload(code)
    payload.update(
        {
            "id": "11111111-1111-1111-1111-111111111107",
            "created_at": datetime(2026, 6, 8, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 8, tzinfo=timezone.utc),
        }
    )
    return payload


class TestJobProfileSchema:
    def test_rejects_dimension_weights_not_equal_one(self) -> None:
        payload = _valid_payload()
        payload["evaluation_dimensions"][0]["weight"] = 0.5

        with pytest.raises(ValueError) as exc:
            JobProfileCreate(**payload)

        assert "权重总和必须等于 1.0" in str(exc.value)

    def test_rejects_invalid_salary_range(self) -> None:
        payload = _valid_payload()
        payload["salary_band"]["base_min"] = 60000

        with pytest.raises(ValueError) as exc:
            JobProfileCreate(**payload)

        assert "base_min 不能大于 base_max" in str(exc.value)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock(return_value=None)
    return db


@pytest.fixture
def service(mock_db):
    return JobProfileService(mock_db)


def _make_profile(profile_id: str = "11111111-1111-1111-1111-111111111107"):
    profile = Mock(spec=JobProfile)
    profile.id = profile_id
    profile.code = "Java_P7"
    profile.title = "高级 Java 工程师"
    profile.level = "P7"
    profile.department = "技术部"
    profile.is_active = True
    profile.created_at = "2026-06-08T00:00:00"
    profile.updated_at = "2026-06-08T00:00:00"
    return profile


class TestJobProfileService:
    async def test_get_by_code(self, service, mock_db) -> None:
        profile = _make_profile()
        result = Mock()
        result.scalar_one_or_none.return_value = profile
        mock_db.execute.return_value = result

        got = await service.get_by_code("Java_P7")

        assert got is profile

    async def test_create_persists_profile(self, service, mock_db) -> None:
        data = JobProfileCreate(**_valid_payload())

        await service.create(data)

        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_db.refresh.called


def _make_app(db_mock) -> FastAPI:
    app = FastAPI()
    app.include_router(job_profiles_router, prefix="/job-profiles")

    async def fake_get_db():
        yield db_mock

    async def fake_org_scoped_db(db=Depends(get_db)):
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[org_scoped_db] = fake_org_scoped_db
    return app


class TestJobProfileApi:
    def test_list_profiles(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.list = AsyncMock(return_value=([_read_payload()], 1))

        with patch("app.api.job_profiles.JobProfileService", return_value=svc):
            resp = TestClient(app).get("/job-profiles")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        svc.list.assert_awaited_once_with(
            skip=0,
            limit=20,
            search=None,
            level=None,
            is_active=None,
        )

    def test_get_profile_by_code_not_found(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.get_by_code = AsyncMock(return_value=None)

        with patch("app.api.job_profiles.JobProfileService", return_value=svc):
            resp = TestClient(app).get("/job-profiles/code/Java_P7")

        assert resp.status_code == 404
        assert "岗位画像不存在" in resp.json()["error"]

    def test_create_profile_conflict(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.get_by_code = AsyncMock(return_value=SimpleNamespace(id="existing"))

        with patch("app.api.job_profiles.JobProfileService", return_value=svc):
            resp = TestClient(app).post("/job-profiles", json=_valid_payload())

        assert resp.status_code == 409
        assert "code 已存在" in resp.json()["error"]

    def test_update_profile_not_found(self) -> None:
        app = _make_app(MagicMock())
        svc = MagicMock()
        svc.update = AsyncMock(return_value=None)

        with patch("app.api.job_profiles.JobProfileService", return_value=svc):
            resp = TestClient(app).put(
                "/job-profiles/11111111-1111-1111-1111-111111111107",
                json={"title": "新标题"},
            )

        assert resp.status_code == 404
