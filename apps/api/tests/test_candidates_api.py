"""Tests for app/api/candidates.py — Candidate CRUD + lifecycle timeline.

覆盖 list/get/create/update/delete + timeline 聚合(创建/投递/评估/面试/反馈事件)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.candidates import router as candidates_router
from app.core.database import get_db
from app.schemas.candidate import CandidateCreate, CandidateUpdate


# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(candidates_router, prefix="/candidates")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _patch_db(app: FastAPI, db_mock):
    async def fake_get_db():
        yield db_mock

    app.dependency_overrides[get_db] = fake_get_db


def _make_candidate(
    id: str = "c1",
    name: str = "Alice",
    source: str = "manual",
    created_at: datetime | None = None,
) -> MagicMock:
    c = MagicMock()
    c.id = id
    c.name = name
    c.source = source
    c.created_at = created_at or datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    c.evaluations = []  # 默认无评估
    return c


# ─── list_candidates (GET /candidates) ────────────────────────────────


class TestListCandidates:
    def test_success(self, app: FastAPI) -> None:
        items = [_candidate_read_dict("c1", "Alice"), _candidate_read_dict("c2", "Bob")]
        db = MagicMock()
        with patch_candidate_service(app, db, list_return=(items, 2)):
            resp = TestClient(app).get("/candidates")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        assert body["items"][0]["name"] == "Alice"
        assert body["skip"] == 0
        assert body["limit"] == 20

    def test_passes_search_and_status(self, app: FastAPI) -> None:
        db = MagicMock()
        with patch_candidate_service(app, db, list_return=([], 0)) as ctx:
            TestClient(app).get(
                "/candidates",
                params={"search": "python", "status": "active", "skip": 5, "limit": 50},
            )

        call = ctx.svc.list.call_args
        assert call.kwargs["search"] == "python"
        assert call.kwargs["status"] == "active"
        assert call.kwargs["skip"] == 5
        assert call.kwargs["limit"] == 50

    def test_empty(self, app: FastAPI) -> None:
        db = MagicMock()
        with patch_candidate_service(app, db, list_return=([], 0)):
            resp = TestClient(app).get("/candidates")

        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []


def _candidate_read_dict(id: str = "c1", name: str = "Alice") -> dict:
    """Build a dict that matches CandidateRead schema."""
    return {
        "id": id,
        "name": name,
        "email": f"{name.lower()}@example.com",
        "phone": None,
        "summary": None,
        "skills": [],
        "experience_years": None,
        "education": None,
        "current_company": None,
        "current_title": None,
        "status": "active",
        "created_at": "2026-06-01T10:00:00+00:00",
        "updated_at": "2026-06-01T10:00:00+00:00",
    }


def patch_candidate_service(app, db, list_return=([], 0), get_return=None, create_return=None, update_return=None, delete_return=None):
    """Helper: patch CandidateService and db, return context manager with .svc attribute."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        items, total = list_return
        mock_svc = AsyncMock()
        mock_svc.list = AsyncMock(return_value=(items, total))
        mock_svc.get_by_id = AsyncMock(return_value=get_return)
        mock_svc.create = AsyncMock(return_value=create_return or {"id": "new"})
        mock_svc.update = AsyncMock(return_value=update_return)
        mock_svc.delete = AsyncMock(return_value=delete_return if delete_return is not None else True)
        _patch_db(app, db)
        with patch("app.api.candidates.CandidateService", return_value=mock_svc):
            yield SimpleNamespace(svc=mock_svc, db=db)

    return _ctx()


# ─── get_candidate (GET /candidates/{id}) ─────────────────────────────


class TestGetCandidate:
    def test_success(self, app: FastAPI) -> None:
        cand = {"id": "c1", "name": "Alice"}
        with patch_candidate_service(app, MagicMock(), get_return=cand):
            resp = TestClient(app).get("/candidates/c1")

        assert resp.status_code == 200
        assert resp.json()["data"] == cand

    def test_not_found(self, app: FastAPI) -> None:
        with patch_candidate_service(app, MagicMock(), get_return=None):
            resp = TestClient(app).get("/candidates/missing")

        assert resp.status_code == 404
        assert "候选人不存在" in resp.json()["error"]


# ─── create_candidate (POST /candidates) ─────────────────────────────


class TestCreateCandidate:
    def test_success(self, app: FastAPI) -> None:
        created = {"id": "c-new", "name": "New Candidate"}
        payload = {"name": "New Candidate", "email": "new@example.com"}
        with patch_candidate_service(app, MagicMock(), create_return=created):
            resp = TestClient(app).post("/candidates", json=payload)

        assert resp.status_code == 201
        assert resp.json()["data"] == created


# ─── update_candidate (PUT /candidates/{id}) ─────────────────────────


class TestUpdateCandidate:
    def test_success(self, app: FastAPI) -> None:
        updated = {"id": "c1", "name": "Updated"}
        with patch_candidate_service(app, MagicMock(), update_return=updated):
            resp = TestClient(app).put(
                "/candidates/c1", json={"name": "Updated"}
            )

        assert resp.status_code == 200
        assert resp.json()["data"] == updated

    def test_not_found(self, app: FastAPI) -> None:
        with patch_candidate_service(app, MagicMock(), update_return=None):
            resp = TestClient(app).put(
                "/candidates/missing", json={"name": "x"}
            )

        assert resp.status_code == 404


# ─── delete_candidate (DELETE /candidates/{id}) ───────────────────────


class TestDeleteCandidate:
    def test_success(self, app: FastAPI) -> None:
        with patch_candidate_service(app, MagicMock(), delete_return=True):
            resp = TestClient(app).delete("/candidates/c1")

        assert resp.status_code == 200
        assert "已删除" in resp.json()["data"]["message"]

    def test_not_found(self, app: FastAPI) -> None:
        with patch_candidate_service(app, MagicMock(), delete_return=False):
            resp = TestClient(app).delete("/candidates/missing")

        assert resp.status_code == 404


# ─── candidate_timeline (GET /candidates/{id}/timeline) ──────────────


def _make_app_for_timeline(db_mock):
    """Return a fresh app wired with the db mock (no auth needed for this endpoint)."""
    app = FastAPI()
    app.include_router(candidates_router, prefix="/candidates")
    _patch_db(app, db_mock)
    return app


def _make_application(
    id: str = "a1",
    job_id: str = "j1",
    status: str = "applied",
    created_at: datetime | None = None,
) -> MagicMock:
    a = MagicMock()
    a.id = id
    a.job_id = job_id
    a.status = status
    a.created_at = created_at or datetime(2026, 6, 1, 11, 0, 0, tzinfo=timezone.utc)
    return a


def _make_job(id: str = "j1", title: str = "Engineer") -> MagicMock:
    j = MagicMock()
    j.id = id
    j.title = title
    return j


def _make_evaluation(
    id: str = "e1",
    overall_score: int = 85,
    created_at: datetime | None = None,
) -> MagicMock:
    e = MagicMock()
    e.id = id
    e.overall_score = overall_score
    e.created_at = created_at or datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
    return e


def _make_interview(
    id: str = "i1",
    type: str = "技术面",
    status: str = "scheduled",
    scheduled_at: datetime | None = None,
) -> MagicMock:
    iv = MagicMock()
    iv.id = id
    iv.type = type
    iv.status = status
    iv.scheduled_at = scheduled_at or datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    return iv


def _make_feedback(
    id: str = "f1",
    interview_id: str = "i1",
    overall_score: int | None = 8,
    created_at: datetime | None = None,
) -> MagicMock:
    f = MagicMock()
    f.id = id
    f.interview_id = interview_id
    f.overall_score = overall_score
    f.created_at = created_at or datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
    return f


def _make_query_results(*results):
    """Create mock query results list and return a side_effect function."""
    iter_results = iter(results)
    async def side_effect(*args, **kwargs):
        r = next(iter_results)
        return r
    return side_effect


def _scalars_result(items):
    r = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=items)
    r.scalars = MagicMock(return_value=scalars)
    return r


def _scalar_one_result(item):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=item)
    return r


class TestCandidateTimeline:
    def test_not_found(self) -> None:
        from app.services.candidate import CandidateService

        db = MagicMock()
        app = _make_app_for_timeline(db)
        with patch.object(CandidateService, "get_by_id", AsyncMock(return_value=None)):
            resp = TestClient(app).get("/candidates/missing/timeline")

        assert resp.status_code == 404

    def test_created_event_only(self) -> None:
        cand = _make_candidate(id="c1", name="Alice", source="referral")
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),  # applications
            _scalars_result([]),  # interviews
            _scalars_result([]),  # interview_evaluations (where(False) still runs)
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["candidate_id"] == "c1"
        assert data["candidate_name"] == "Alice"
        assert data["total"] == 1
        event = data["events"][0]
        assert event["type"] == "created"
        assert event["status"] == "completed"
        assert event["metadata"]["source"] == "referral"

    def test_application_with_job(self) -> None:
        cand = _make_candidate()
        app_obj = _make_application(job_id="j1", status="applied")
        job = _make_job(title="高级工程师")
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([app_obj]),  # applications
            _scalar_one_result(job),     # job query
            _scalars_result([]),         # interviews
            _scalars_result([]),         # interview_evaluations
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        data = resp.json()["data"]
        events_by_type = {e["type"]: e for e in data["events"]}
        assert "application" in events_by_type
        app_event = events_by_type["application"]
        assert "高级工程师" in app_event["title"]
        assert app_event["status"] == "in_progress"
        assert app_event["metadata"]["status"] == "applied"
        assert app_event["metadata"]["job_id"] == "j1"

    def test_application_completed_status(self) -> None:
        """offered/hired/rejected → application event status = completed."""
        cand = _make_candidate()
        for final_status in ("offered", "hired", "rejected"):
            app_obj = _make_application(status=final_status)
            db = MagicMock()
            db.execute = AsyncMock(side_effect=[
                _scalars_result([app_obj]),
                _scalar_one_result(_make_job()),
                _scalars_result([]),
                _scalars_result([]),
            ])
            app = _make_app_for_timeline(db)
            with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
                resp = TestClient(app).get("/candidates/c1/timeline")
            event = next(e for e in resp.json()["data"]["events"] if e["type"] == "application")
            assert event["status"] == "completed", f"status={final_status} should be completed"

    def test_application_without_job(self) -> None:
        """application.job_id 为空 → 不查 job, title 显示 '未知'."""
        cand = _make_candidate()
        app_obj = _make_application(job_id=None)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([app_obj]),  # applications
            _scalars_result([]),         # interviews
            _scalars_result([]),         # interview_evaluations
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        event = next(e for e in resp.json()["data"]["events"] if e["type"] == "application")
        assert "未知" in event["title"]

    def test_evaluation_events_from_candidate(self) -> None:
        """candidate.evaluations 非空 → 添加 evaluation 事件."""
        cand = _make_candidate()
        cand.evaluations = [
            _make_evaluation(id="e1", overall_score=90),
            _make_evaluation(id="e2", overall_score=75),
        ]
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),
            _scalars_result([]),
            _scalars_result([]),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        evals = [e for e in resp.json()["data"]["events"] if e["type"] == "evaluation"]
        assert len(evals) == 2
        assert evals[0]["metadata"]["score"] == 90
        assert "90/100" in evals[0]["description"]

    def test_interview_scheduled(self) -> None:
        cand = _make_candidate()
        iv = _make_interview(status="scheduled", type="技术面")
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),
            _scalars_result([iv]),
            _scalars_result([]),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        events = resp.json()["data"]["events"]
        iv_event = next(e for e in events if e["type"] == "interview")
        assert iv_event["title"] == "面试安排"
        assert iv_event["status"] == "pending"
        assert iv_event["metadata"]["type"] == "技术面"

    def test_interview_completed(self) -> None:
        cand = _make_candidate()
        iv = _make_interview(status="completed")
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),
            _scalars_result([iv]),
            _scalars_result([]),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        iv_event = next(e for e in resp.json()["data"]["events"] if e["type"] == "interview")
        assert iv_event["title"] == "面试完成"
        assert iv_event["status"] == "completed"

    def test_interview_cancelled(self) -> None:
        """cancelled 也算 completed status."""
        cand = _make_candidate()
        iv = _make_interview(status="cancelled")
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),
            _scalars_result([iv]),
            _scalars_result([]),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        iv_event = next(e for e in resp.json()["data"]["events"] if e["type"] == "interview")
        assert iv_event["status"] == "completed"

    def test_feedback_events(self) -> None:
        cand = _make_candidate()
        iv = _make_interview(id="i1")
        fb = _make_feedback(interview_id="i1", overall_score=9)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),
            _scalars_result([iv]),
            _scalars_result([fb]),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        fb_events = [e for e in resp.json()["data"]["events"] if e["type"] == "feedback"]
        assert len(fb_events) == 1
        assert "9/10" in fb_events[0]["description"]
        assert fb_events[0]["metadata"]["score"] == 9

    def test_feedback_null_score(self) -> None:
        """feedback.overall_score 为 None → 显示 N/A."""
        cand = _make_candidate()
        iv = _make_interview(id="i1")
        fb = _make_feedback(interview_id="i1", overall_score=None)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),
            _scalars_result([iv]),
            _scalars_result([fb]),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        fb_event = next(e for e in resp.json()["data"]["events"] if e["type"] == "feedback")
        assert "N/A" in fb_event["description"]

    def test_feedback_query_exception_returns_empty(self) -> None:
        """interview_evals 查询异常 → 评估列表为空(容错)."""
        cand = _make_candidate()
        iv = _make_interview(id="i1")
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),
            _scalars_result([iv]),
            RuntimeError("DB error"),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        assert resp.status_code == 200
        fb_events = [e for e in resp.json()["data"]["events"] if e["type"] == "feedback"]
        assert fb_events == []

    def test_interview_evals_always_queried(self) -> None:
        """interview_evaluations 查询总会执行(用 where(False) if no interviews)."""
        cand = _make_candidate()
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),
            _scalars_result([]),
            _scalars_result([]),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            TestClient(app).get("/candidates/c1/timeline")

        assert db.execute.await_count == 3

    def test_events_sorted_ascending_by_timestamp(self) -> None:
        """事件按 timestamp 升序排列."""
        cand = _make_candidate(created_at=datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc))
        app_obj = _make_application(
            created_at=datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc)
        )
        iv = _make_interview(
            scheduled_at=datetime(2026, 6, 5, 14, 0, 0, tzinfo=timezone.utc)
        )
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([app_obj]),
            _scalar_one_result(_make_job()),
            _scalars_result([iv]),
            _scalars_result([]),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        events = resp.json()["data"]["events"]
        types = [e["type"] for e in events]
        assert types == ["created", "application", "interview"]

    def test_null_timestamps_handled(self) -> None:
        """created_at / scheduled_at 为 None → timestamp 字段是空字符串."""
        cand = _make_candidate()
        cand.created_at = None  # 覆盖默认时间戳,模拟空值
        iv = _make_interview()
        iv.scheduled_at = None  # 显式置空
        cand.evaluations = [_make_evaluation()]
        cand.evaluations[0].created_at = None
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_result([]),
            _scalars_result([iv]),
            _scalars_result([]),
        ])
        app = _make_app_for_timeline(db)
        with patch("app.services.candidate.CandidateService.get_by_id", AsyncMock(return_value=cand)):
            resp = TestClient(app).get("/candidates/c1/timeline")

        events = resp.json()["data"]["events"]
        for e in events:
            assert e["timestamp"] == ""
