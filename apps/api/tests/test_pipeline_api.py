"""Pipeline API + ScreeningService tests — mock at service/LLM level."""

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

    def test_screen_resume_returns_200(self, client):
        """POST /screen-resume returns ScreeningResult shape."""
        with patch("app.api.pipeline.service.screen_resume") as mock_screen:
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

    def test_screen_resume_validates_input(self, client):
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

    def test_screen_resume_uses_service_correctly(self, client):
        """Verify the service is called with correct arguments."""
        with patch("app.api.pipeline.service.screen_resume") as mock_screen:
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
        assert isinstance(data, list)
        if data:
            assert "name" in data[0]
            assert "scores" in data[0]

    def test_list_evaluations_empty_db(self, client, app, override_get_db, mock_db_session):
        """GET /evaluations returns empty list when no data."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db_session.execute.return_value = mock_result

        resp = client.get("/evaluations")

        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_list_evaluations_db_error(self, client, app, override_get_db, mock_db_session):
        """GET /evaluations returns empty list on DB error."""
        mock_db_session.execute.side_effect = Exception("DB down")

        resp = client.get("/evaluations")

        assert resp.status_code == 200
        data = resp.json()
        assert data == []


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

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "error" in data

    def test_generate_report_missing_candidate_id(self, client, app):
        """POST /generate-report without candidate_id returns error."""
        resp = client.post(
            "/generate-report",
            json={"application_id": "app-1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_generate_report_missing_application_id(self, client, app):
        """POST /generate-report without application_id returns error."""
        resp = client.post(
            "/generate-report",
            json={"candidate_id": "cand-1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
