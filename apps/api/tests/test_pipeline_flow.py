"""Phase 1.1 全链路测试 — 状态机校验 + 流水线 + ReportService 串联 + 边界检查。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
def mock_db_session():
    return AsyncMock()


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.pipeline import router

    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def override_get_db(app, mock_db_session):
    from app.core.database import get_db

    async def _mock_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


# ── helper: build a mock candidate ──────────────────────────────────────────


def _mock_candidate(id="c1", status="evaluating"):
    c = MagicMock()
    c.id = id
    c.status = status
    return c


# ── Happy paths ─────────────────────────────────────────────────────────────


class TestPipelineFlowHappy:
    """全链路正常场景。"""

    DEFAULT_RESULT = {
        "pipeline_id": "p1",
        "candidate_id": "c1",
        "job_id": "j1",
        "overall_score": 85,
        "dimensions": {},
        "parsed_resume": {},
        "gate_passed": True,
        "needs_human_review": False,
        "strengths": ["Python"],
        "weaknesses": [],
        "recommendation": "推荐",
        "summary": "通过",
        "steps": [],
    }

    def test_screen_resume_full_flow(self, client, override_get_db, mock_db_session):
        """完整链路: application_id → report 生成 → application 更新。"""
        candidate_svc = AsyncMock()
        candidate_svc.start_screening.return_value = _mock_candidate()

        with (
            patch("app.api.pipeline.CandidateService", return_value=candidate_svc),
            patch("app.api.pipeline.ReportService") as MockReportSvc,
            patch("app.api.pipeline.ApplicationService") as MockAppSvc,
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.return_value = self.DEFAULT_RESULT

            mock_report_svc = AsyncMock()
            mock_report_svc.generate_report.return_value = {
                "candidate_name": "Alice",
                "overall_score": 85,
                "summary": "Good candidate",
            }
            MockReportSvc.return_value = mock_report_svc

            mock_app_svc = AsyncMock()
            MockAppSvc.return_value = mock_app_svc

            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "John Python",
                    "job_requirements": "Python dev",
                    "application_id": "app-1",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["gate_passed"] is True
        assert data["overall_score"] == 85
        assert data["report"] is not None
        assert data["report"]["candidate_name"] == "Alice"
        assert data["candidate_status"] == "evaluated"

        # Verify call order
        candidate_svc.start_screening.assert_called_once_with("c1")
        mock_screen.assert_called_once_with(
            candidate_id="c1", job_id="j1",
            resume_text="John Python", job_requirements="Python dev",
        )
        mock_report_svc.generate_report.assert_called_once_with("c1", "app-1")
        candidate_svc.complete_screening.assert_called_once_with("c1", True)
        mock_app_svc.update.assert_called_once()

    def test_screen_resume_no_application_id(self, client, override_get_db, mock_db_session):
        """无 application_id: 不生成报告，不同步申请。"""
        candidate_svc = AsyncMock()
        candidate_svc.start_screening.return_value = _mock_candidate()

        with (
            patch("app.api.pipeline.CandidateService", return_value=candidate_svc),
            patch("app.api.pipeline.ReportService") as MockReportSvc,
            patch("app.api.pipeline.ApplicationService") as MockAppSvc,
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.return_value = self.DEFAULT_RESULT

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
        assert data["success"] is True
        assert data["gate_passed"] is True
        assert data["report"] is None
        assert data["candidate_status"] == "evaluated"

        candidate_svc.complete_screening.assert_called_once_with("c1", True)
        MockReportSvc.assert_not_called()
        MockAppSvc.assert_not_called()

    def test_screen_resume_gate_failed(self, client, override_get_db, mock_db_session):
        """Gate 不通过: candidate_status = failed, application 同步为 rejected。"""
        candidate_svc = AsyncMock()
        candidate_svc.start_screening.return_value = _mock_candidate()

        result = dict(self.DEFAULT_RESULT)
        result["gate_passed"] = False
        result["overall_score"] = 35
        result["needs_human_review"] = True

        with (
            patch("app.api.pipeline.CandidateService", return_value=candidate_svc),
            patch("app.api.pipeline.ApplicationService") as MockAppSvc,
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.return_value = result

            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "bad cv",
                    "job_requirements": "Python dev",
                    "application_id": "app-1",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["gate_passed"] is False
        assert data["candidate_status"] == "failed"
        candidate_svc.complete_screening.assert_called_once_with("c1", False)


# ── Error / boundary paths ──────────────────────────────────────────────────


class TestPipelineFlowErrors:
    """边界与异常场景。"""

    DEFAULT_RESULT = {
        "pipeline_id": "p1",
        "candidate_id": "c1",
        "job_id": "j1",
        "overall_score": 85,
        "dimensions": {},
        "parsed_resume": {},
        "gate_passed": True,
        "needs_human_review": False,
        "strengths": ["Python"],
        "weaknesses": [],
        "recommendation": "推荐",
        "summary": "通过",
        "steps": [],
    }

    def test_candidate_not_found(self, client, override_get_db, mock_db_session):
        """候选人不存在 → 404。"""
        candidate_svc = AsyncMock()
        candidate_svc.start_screening.return_value = None

        with patch("app.api.pipeline.CandidateService", return_value=candidate_svc):
            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "nonexistent",
                    "job_id": "j1",
                    "resume_text": "any",
                    "job_requirements": "any",
                },
            )

        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_wrong_state_transition(self, client, override_get_db, mock_db_session):
        """状态机校验不通过 → 400。"""
        candidate_svc = AsyncMock()
        candidate_svc.start_screening.side_effect = ValueError(
            "候选人状态 'archived' 不允许开始初筛"
        )

        with patch("app.api.pipeline.CandidateService", return_value=candidate_svc):
            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "any",
                    "job_requirements": "any",
                },
            )

        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body
        assert "archived" in body["detail"]

    def test_pipeline_execution_fails_returns_graceful_result(
        self, client, override_get_db, mock_db_session
    ):
        """流水线执行异常 → 返回 success=False + candidate_status=failed。"""
        candidate_svc = AsyncMock()
        candidate_svc.start_screening.return_value = _mock_candidate()

        with (
            patch("app.api.pipeline.CandidateService", return_value=candidate_svc),
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.side_effect = RuntimeError("LLM provider unavailable")

            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "any",
                    "job_requirements": "any",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["gate_passed"] is False
        assert data["candidate_status"] == "failed"
        assert "系统错误" in data["recommendation"]
        # complete_screening should be called with False by the except handler
        candidate_svc.complete_screening.assert_called_once_with("c1", False)

    def test_report_failure_is_non_blocking(
        self, client, override_get_db, mock_db_session
    ):
        """报告生成失败 → report=None, 不阻塞。"""
        candidate_svc = AsyncMock()
        candidate_svc.start_screening.return_value = _mock_candidate()

        with (
            patch("app.api.pipeline.CandidateService", return_value=candidate_svc),
            patch("app.api.pipeline.ReportService") as MockReportSvc,
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.return_value = self.DEFAULT_RESULT

            mock_report_svc = AsyncMock()
            mock_report_svc.generate_report.side_effect = RuntimeError("LLM down")
            MockReportSvc.return_value = mock_report_svc

            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "any",
                    "job_requirements": "any",
                    "application_id": "app-1",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True  # Pipeline itself succeeded
        assert data["report"] is None  # Report failure swallowed
        assert data["candidate_status"] == "evaluated"

    def test_application_sync_failure_is_non_blocking(
        self, client, override_get_db, mock_db_session
    ):
        """申请状态同步失败 → pipeline 仍成功。"""
        candidate_svc = AsyncMock()
        candidate_svc.start_screening.return_value = _mock_candidate()

        with (
            patch("app.api.pipeline.CandidateService", return_value=candidate_svc),
            patch("app.api.pipeline.ApplicationService") as MockAppSvc,
            patch("app.api.pipeline.service.screen_resume") as mock_screen,
        ):
            mock_screen.return_value = self.DEFAULT_RESULT

            mock_app_svc = AsyncMock()
            mock_app_svc.update.side_effect = RuntimeError("DB timeout")
            MockAppSvc.return_value = mock_app_svc

            resp = client.post(
                "/screen-resume",
                json={
                    "candidate_id": "c1",
                    "job_id": "j1",
                    "resume_text": "any",
                    "job_requirements": "any",
                    "application_id": "app-1",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["candidate_status"] == "evaluated"
