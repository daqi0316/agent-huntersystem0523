"""Pipeline API + ScreeningService tests — mock at service/LLM level."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.chat = AsyncMock()
    return llm


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.pipeline import router

    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


# ── ScreeningService tests ──────────────────────────────────────────────────


class TestScreeningService:
    async def test_screen_resume_success(self, mock_llm):
        mock_llm.chat.side_effect = [
            '{"name": "John", "skills": ["Python"]}',
            '{"overall_score": 8, "strengths": ["Python"], "weaknesses": [], "recommendation": "推荐"}',
            '{"gate_passed": true, "score_adjusted": 8, "issues": [], "needs_human_review": false, "gate_summary": "通过"}',
        ]
        with patch("app.agents.pipeline.get_llm_client", return_value=mock_llm):
            from app.services.screening import ScreeningService

            result = await ScreeningService().screen_resume(
                candidate_id="cand-1",
                job_id="job-1",
                resume_text="John Python",
                job_requirements="Python dev",
            )
        assert result["overall_score"] == 8
        assert result["gate_passed"] is True
        assert result["recommendation"] == "推荐"
        assert result["pipeline_id"]

    async def test_screen_resume_fallback_on_failure(self, mock_llm):
        mock_llm.chat.side_effect = RuntimeError("LLM down")
        with patch("app.agents.pipeline.get_llm_client", return_value=mock_llm):
            from app.services.screening import ScreeningService

            result = await ScreeningService().screen_resume(
                candidate_id="cand-1",
                job_id="job-1",
                resume_text="any",
                job_requirements="any",
            )
        assert result["overall_score"] == 0
        assert result["gate_passed"] is False
        assert result["needs_human_review"] is True
        assert "人工处理" in result["recommendation"]


# ── API route tests ─────────────────────────────────────────────────────────


class TestScreenResumeAPI:
    ROUTE = "/screen-resume"

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.fixture
    def override_get_db(self, app, mock_db_session):
        from app.core.database import get_db

        async def _mock_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = _mock_get_db
        yield
        app.dependency_overrides.pop(get_db, None)

    def _make_mock_candidate_service(self, candidate_exists=True):
        """Helper: build a patched CandidateService returning a mock candidate."""
        svc = AsyncMock()
        if candidate_exists:
            mock_candidate = MagicMock()
            mock_candidate.id = "c1"
            mock_candidate.status = "evaluating"
            svc.start_screening.return_value = mock_candidate
        else:
            svc.start_screening.return_value = None
        return svc

    def test_screen_resume_returns_200(self, client, override_get_db, mock_db_session):
        """POST /screen-resume returns ScreeningResult shape."""
        mock_candidate_svc = self._make_mock_candidate_service()
        with (
            patch("app.api.pipeline.CandidateService", return_value=mock_candidate_svc),
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.return_value = {
                "pipeline_id": "abc",
                "candidate_id": "c1",
                "job_id": "j1",
                "overall_score": 8,
                "dimensions": {},
                "parsed_resume": {},
                "gate_passed": True,
                "needs_human_review": False,
                "strengths": [],
                "weaknesses": [],
                "recommendation": "推荐",
                "summary": "通过",
                "steps": [],
            }
            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "John Python",
                    "job_requirements": "Python dev",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["gate_passed"] is True
        assert data["overall_score"] == 8
        assert data["recommendation"] == "推荐"
        mock_candidate_svc.start_screening.assert_called_once_with("c1")
        mock_candidate_svc.complete_screening.assert_called_once_with("c1", True)

    def test_screen_resume_validates_input(self, client, override_get_db):
        """Missing required fields return 422."""
        resp = client.post("/screen-resume", json={"candidate_id": "c1"})
        assert resp.status_code == 422

    def test_pipeline_progress_returns_progress(self, client):
        """GET /{pipeline_id}/progress returns progress."""
        with patch("app.api.pipeline.service.get_pipeline_progress") as mock_progress:
            mock_progress.return_value = {
                "pipeline_id": "abc",
                "status": "completed",
                "progress": 1.0,
                "current_step": "done",
                "steps": [],
            }
            resp = client.get("/abc/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["progress"] == 1.0

    def test_screen_resume_uses_service_correctly(self, client, override_get_db, mock_db_session):
        """Verify the service is called with correct arguments."""
        mock_candidate_svc = self._make_mock_candidate_service()
        with (
            patch("app.api.pipeline.CandidateService", return_value=mock_candidate_svc),
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.return_value = {
                "pipeline_id": "x",
                "candidate_id": "c1",
                "job_id": "j1",
                "overall_score": 8,
                "dimensions": {},
                "parsed_resume": {},
                "gate_passed": True,
                "needs_human_review": False,
                "strengths": [],
                "weaknesses": [],
                "recommendation": "推荐",
                "summary": "好",
                "steps": [],
            }
            client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "some text",
                    "job_requirements": "some req",
                },
            )
        mock_screen.assert_called_once_with(
            candidate_id="c1",
            job_id="j1",
            resume_text="some text",
            job_requirements="some req",
        )

    # ── Coverage edge: pipeline_task_id → progress store writes ──────

    def test_screen_resume_with_pipeline_task_id(self, client, override_get_db, mock_db_session):
        pipeline_id = "test-task-123"
        mock_candidate_svc = self._make_mock_candidate_service()
        with (
            patch("app.api.pipeline.CandidateService", return_value=mock_candidate_svc),
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.return_value = {
                "pipeline_id": pipeline_id,
                "candidate_id": "c1", "job_id": "j1",
                "overall_score": 7, "dimensions": {}, "parsed_resume": {},
                "gate_passed": True, "needs_human_review": False,
                "strengths": [], "weaknesses": [], "recommendation": "OK",
                "summary": "通过", "steps": [],
            }
            from app.api.pipeline import _pipeline_store
            _pipeline_store.clear()
            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "text",
                    "job_requirements": "req",
                    "pipeline_task_id": pipeline_id,
                },
            )
        assert resp.status_code == 200
        assert pipeline_id in _pipeline_store
        assert _pipeline_store[pipeline_id]["status"] == "completed"

    # ── Coverage edge: application_id → report gen + app sync ────────

    def test_screen_resume_with_application_id(self, client, override_get_db, mock_db_session):
        mock_candidate_svc = self._make_mock_candidate_service()
        with (
            patch("app.api.pipeline.CandidateService", return_value=mock_candidate_svc),
            patch("app.api.pipeline.ReportService") as MockReportSvc,
            patch("app.api.pipeline.ApplicationService") as MockAppSvc,
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_report = AsyncMock()
            mock_report.generate_report.return_value = {"report": "ok"}
            MockReportSvc.return_value = mock_report
            MockAppSvc.return_value = AsyncMock()

            mock_screen.return_value = {
                "pipeline_id": "x", "candidate_id": "c1", "job_id": "j1",
                "overall_score": 8, "dimensions": {}, "parsed_resume": {},
                "gate_passed": True, "needs_human_review": False,
                "strengths": [], "weaknesses": [], "recommendation": "推荐",
                "summary": "通过", "steps": [],
            }
            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "text",
                    "job_requirements": "req",
                    "application_id": "app-123",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["report"] == {"report": "ok"}

    # ── Coverage edge: candidate not found (404) ─────────────────────

    def test_screen_resume_candidate_not_found(self, client, override_get_db):
        mock_candidate_svc = self._make_mock_candidate_service(candidate_exists=False)
        with patch("app.api.pipeline.CandidateService", return_value=mock_candidate_svc):
            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "nonexistent",
                    "job_id": "j1",
                    "resume_text": "text",
                    "job_requirements": "req",
                },
            )
        assert resp.status_code == 404

    # ── Coverage edge: start_screening raises ValueError (400) ───────

    def test_screen_resume_invalid_status(self, client, override_get_db):
        mock_candidate_svc = self._make_mock_candidate_service()
        mock_candidate_svc.start_screening.side_effect = ValueError("状态不允许")
        with patch("app.api.pipeline.CandidateService", return_value=mock_candidate_svc):
            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "text",
                    "job_requirements": "req",
                },
            )
        assert resp.status_code == 400

    # ── Coverage edge: screen_resume service raises Exception ────────

    def test_screen_resume_service_exception(self, client, override_get_db, mock_db_session):
        mock_candidate_svc = self._make_mock_candidate_service()
        with (
            patch("app.api.pipeline.CandidateService", return_value=mock_candidate_svc),
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.side_effect = RuntimeError("LLM crashed")
            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "text",
                    "job_requirements": "req",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["gate_passed"] is False
        assert data["needs_human_review"] is True
        assert "系统错误" in data["recommendation"]


class TestProgressAndStreamAPI:
    ROUTE = "/{task_id}/progress"

    def test_pipeline_progress_from_store(self, client):
        from app.api.pipeline import _pipeline_store
        _pipeline_store.clear()
        _pipeline_store["stored-id"] = {
            "pipeline_id": "stored-id",
            "status": "running",
            "progress": 0.5,
            "current_step": "match",
            "step_label": "职位匹配",
            "step_description": "匹配中",
            "updated_at": datetime.now().isoformat(),
        }
        resp = client.get("/stored-id/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["progress"] == 0.5
        _pipeline_store.clear()

    def test_pipeline_progress_from_service(self, client):
        with patch("app.api.pipeline.service.get_pipeline_progress") as mock_progress:
            mock_progress.return_value = {
                "pipeline_id": "svc-id",
                "status": "completed",
                "progress": 1.0,
                "current_step": "done",
                "steps": [],
            }
            resp = client.get("/svc-id/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    def test_pipeline_stream_returns_events(self, client):
        import app.api.pipeline as pipeline_module
        pipeline_module._pipeline_store.clear()
        task_id = "stream-test-id"
        pipeline_module._pipeline_store[task_id] = {
            "pipeline_id": task_id,
            "status": "completed",
            "progress": 1.0,
            "current_step": "done",
            "step_label": "完成",
            "step_description": "流水线执行完成",
            "updated_at": datetime.now().isoformat(),
        }
        resp = client.get(f"/{task_id}/stream")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        events = resp.text.strip().split("\n\n")
        assert len(events) >= 1
        for event in events:
            if not event.strip():
                continue
            assert event.startswith("data: ")
            payload = json.loads(event.replace("data: ", "", 1))
            assert "pipeline_id" in payload
            assert "status" in payload
        pipeline_module._pipeline_store.clear()


class TestListEvaluationsAPI:
    ROUTE = "/evaluations"

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.fixture
    def override_get_db(self, app, mock_db_session):
        from app.core.database import get_db

        async def _mock_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = _mock_get_db
        yield
        app.dependency_overrides.pop(get_db, None)

    def test_list_evaluations_returns_list(self, client, app, override_get_db, mock_db_session):
        """GET /evaluations returns evaluations list."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__.side_effect = lambda idx: [
            "cand-1", "Alice", "Engineer", "Acme",
            ["Python"], "active", "Good",             datetime(2025, 1, 15),
        ][idx]
        mock_row._mapping = {
            "id": "cand-1",
            "name": "Alice",
            "current_title": "Engineer",
            "current_company": "Acme",
            "skills": ["Python"],
            "status": "active",
            "summary": "Good",
            "created_at": datetime(2025, 1, 15),
        }
        mock_result.fetchall.return_value = [mock_row]
        mock_db_session.execute.return_value = mock_result

        resp = client.get("/evaluations")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        if data["data"]:
            assert "name" in data["data"][0]
            assert "scores" in data["data"][0]

    def test_list_evaluations_empty_db(self, client, app, override_get_db, mock_db_session):
        """GET /evaluations returns empty list when no data."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db_session.execute.return_value = mock_result

        resp = client.get("/evaluations")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] == []

    def test_list_evaluations_db_error(self, client, app, override_get_db, mock_db_session):
        """GET /evaluations returns error response on DB error."""
        mock_db_session.execute.side_effect = Exception("DB down")

        resp = client.get("/evaluations")

        data = resp.json()
        assert data["success"] is False
        assert "error" in data


class TestGenerateReportAPI:
    ROUTE = "/generate-report"

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.fixture
    def override_get_db(self, app, mock_db_session):
        from app.core.database import get_db

        async def _mock_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = _mock_get_db
        yield
        app.dependency_overrides.pop(get_db, None)

    def test_generate_report_success(self, client, app, override_get_db, mock_db_session):
        """POST /generate-report returns report data."""
        with patch("app.api.pipeline.ReportService", create=True) as MockReportService:
            mock_service = AsyncMock()
            MockReportService.return_value = mock_service
            mock_service.generate_report.return_value = {
                "candidate_name": "Alice",
                "score_dimensions": [],
                "overall_score": 80,
                "summary": "Good",
                "llm_generated": True,
            }

            resp = client.post(
                "/generate-report",
                json={
                    "candidate_id": "cand-1",
                    "application_id": "app-1",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["candidate_name"] == "Alice"

    def test_generate_report_missing_fields(self, client, app):
        """POST /generate-report with missing fields returns error."""
        resp = client.post("/generate-report", json={})

        data = resp.json()
        assert data["success"] is False
        assert "error" in data

    def test_generate_report_missing_candidate_id(self, client, app):
        """POST /generate-report without candidate_id returns error."""
        resp = client.post(
            "/generate-report",
            json={"application_id": "app-1"},
        )

        data = resp.json()
        assert data["success"] is False

    def test_generate_report_missing_application_id(self, client, app):
        """POST /generate-report without application_id returns error."""
        resp = client.post(
            "/generate-report",
            json={"candidate_id": "cand-1"},
        )

        data = resp.json()
        assert data["success"] is False
