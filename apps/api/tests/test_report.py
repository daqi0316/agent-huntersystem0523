"""Report service tests: evaluation report generation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestReportServiceUnit:
    """Unit tests for ReportService (_keyword_generate logic)."""

    @pytest.mark.asyncio
    async def test_report_service_initialization(self):
        """ReportService can be instantiated with a mock db."""
        from app.services.report import ReportService

        class MockDB:
            pass

        service = ReportService(MockDB())
        assert service is not None
        assert len(service._keyword_generate(None, None)["score_dimensions"]) == 8

    def test_keyword_generate_returns_all_dimensions(self):
        """_keyword_generate returns 8 dimensions with scores."""
        from app.services.report import ReportService, DIMENSION_NAMES

        class MockDB:
            pass

        service = ReportService(MockDB())
        result = service._keyword_generate(None, None)

        assert len(result["score_dimensions"]) == 8
        assert result["overall_score"] > 0
        assert "LLM" in result["summary"] or "降级" in result["summary"]

        for dim in result["score_dimensions"]:
            assert dim["name"] in DIMENSION_NAMES
            assert 0 <= dim["score"] <= 100
            assert dim["reason"]

    def test_keyword_generate_skill_bonus(self):
        """Skill count increases the 专业技能 score."""
        from app.services.report import ReportService

        class MockCandidate:
            name = "Test"
            skills = ["Python", "Java", "Go", "Kubernetes", "Docker"]
            experience_years = 5
            current_title = "Senior Engineer"
            current_company = "Acme"
            summary = "Experienced engineer"

        class MockDB:
            pass

        service = ReportService(MockDB())
        result = service._keyword_generate(MockCandidate(), None)

        skill_dim = next(d for d in result["score_dimensions"] if d["name"] == "专业技能")
        assert skill_dim["score"] >= 80

    @pytest.mark.asyncio
    async def test_report_generate_llm_fallback(self):
        """generate_report falls back to keyword scoring when LLM fails."""
        from app.services.report import ReportService

        mock_candidate = MagicMock()
        mock_candidate.name = "Test Candidate"
        mock_candidate.skills = ["Python"]
        mock_candidate.experience_years = 3
        mock_candidate.current_title = "Engineer"
        mock_candidate.current_company = "Acme"
        mock_candidate.summary = "Good engineer"

        service = ReportService(AsyncMock())

        with patch.object(service, "_load_data", return_value=(mock_candidate, None, None)):
            with patch.object(service, "_llm_generate", side_effect=Exception("LLM failed")):
                result = await service.generate_report("some-id", "some-app")

        assert result["candidate_name"] == "Test Candidate"
        assert result["llm_generated"] is False
        assert len(result["score_dimensions"]) == 8


class TestReportServiceExtended:
    """Extended tests covering _load_data, _parse_llm_response, get_report."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        from app.services.report import ReportService

        return ReportService(mock_db)

    @pytest.mark.asyncio
    async def test_load_data_candidate_found(self, service, mock_db):
        """_load_data returns candidate, application, and job."""
        mock_candidate = MagicMock()
        mock_candidate.id = "cand-1"
        mock_app = MagicMock()
        mock_app.id = "app-1"
        mock_app.job_id = "job-1"
        mock_job = MagicMock()
        mock_job.id = "job-1"

        mock_result_c = MagicMock()
        mock_result_c.scalar_one_or_none.return_value = mock_candidate
        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none.return_value = mock_app
        mock_result_j = MagicMock()
        mock_result_j.scalar_one_or_none.return_value = mock_job

        mock_db.execute.side_effect = [mock_result_c, mock_result_a, mock_result_j]

        candidate, application, job = await service._load_data("cand-1", "app-1")

        assert candidate is mock_candidate
        assert application is mock_app
        assert job is mock_job

    @pytest.mark.asyncio
    async def test_load_data_candidate_not_found(self, service, mock_db):
        """_load_data returns None for unfound entities."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        candidate, application, job = await service._load_data("nonexistent", "nonexistent")

        assert candidate is None
        assert application is None
        assert job is None

    def test_parse_llm_response_plain_json(self, service):
        """_parse_llm_response handles plain JSON."""
        response = '{"score_dimensions": [{"name": "专业技能", "score": 80, "reason": "ok"}], "overall_score": 80, "summary": "Good"}'
        result = service._parse_llm_response(response)
        assert result["overall_score"] == 80
        assert len(result["score_dimensions"]) == 1

    def test_parse_llm_response_markdown_fence(self, service):
        """_parse_llm_response extracts JSON from markdown fences."""
        response = '```json\n{"score_dimensions": [], "overall_score": 75, "summary": "Ok"}\n```'
        result = service._parse_llm_response(response)
        assert result["overall_score"] == 75

    def test_parse_llm_response_broken_json(self, service):
        """_parse_llm_response falls back when JSON is broken."""
        response = "this is not json at all{{{"
        result = service._parse_llm_response(response)
        assert len(result["score_dimensions"]) == 8

    def test_keyword_generate_experience_bonus(self, service):
        """Experience years increase 经验匹配 score."""
        mock_candidate = MagicMock()
        mock_candidate.name = "Test"
        mock_candidate.skills = []
        mock_candidate.experience_years = 10
        mock_candidate.current_title = "Senior"
        mock_candidate.current_company = "Acme"
        mock_candidate.summary = "Experienced"

        result = service._keyword_generate(mock_candidate, None)
        exp_dim = next(d for d in result["score_dimensions"] if d["name"] == "经验匹配")
        assert exp_dim["score"] >= 85

    def test_keyword_generate_default_scores(self, service):
        """_keyword_generate with None candidate uses defaults."""
        from app.services.report import DEFAULT_KEYWORD_SCORE

        result = service._keyword_generate(None, None)
        skill_dim = next(d for d in result["score_dimensions"] if d["name"] == "专业技能")
        assert skill_dim["score"] == DEFAULT_KEYWORD_SCORE["专业技能"]

    @pytest.mark.asyncio
    async def test_generate_report_llm_success(self, service, mock_db):
        """generate_report returns LLM results when LLM succeeds."""
        mock_candidate = MagicMock()
        mock_candidate.name = "LLM Candidate"
        mock_candidate.skills = ["Python"]
        mock_candidate.experience_years = 3
        mock_candidate.current_title = "Dev"
        mock_candidate.current_company = "Co"
        mock_candidate.summary = "Good"

        mock_job = MagicMock()
        mock_job.title = "Engineer"
        mock_job.department = "Engineering"
        mock_job.requirements = "Python"

        mock_app = MagicMock()
        mock_app.match_score = 0.0
        mock_app.ai_summary = ""
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        with patch.object(service, "_load_data", return_value=(mock_candidate, mock_app, mock_job)):
            with patch.object(service, "_llm_generate", return_value={
                "score_dimensions": [{"name": "专业技能", "score": 90, "reason": "ok"}],
                "overall_score": 90,
                "summary": "Excellent",
            }):
                result = await service.generate_report("cand-1", "app-1")

        assert result["candidate_name"] == "LLM Candidate"
        assert result["job_title"] == "Engineer"
        assert result["llm_generated"] is True
        assert result["overall_score"] == 90
        assert mock_app.match_score == 0.9
        assert mock_app.ai_summary == "Excellent"

    @pytest.mark.asyncio
    async def test_get_report_returns_expected_structure(self, service):
        """get_report returns status dict."""
        result = await service.get_report("report-123")
        assert result["report_id"] == "report-123"
        assert result["status"] == "available"
