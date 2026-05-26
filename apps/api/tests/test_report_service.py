from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from app.services.report import ReportService


class TestReport:
    async def test_llm_property_lazy_init(self):
        mock_db = AsyncMock()
        svc = ReportService(mock_db)
        assert svc._llm is None
        _ = svc.llm
        assert svc._llm is not None

    async def test_generate_report_with_rollback(self):
        """LLM succeeds but updating application fails → rollback is called."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = Mock()

        # Setup load_data results
        from app.models.candidate import Candidate
        from app.models.application import Application

        candidate = Mock(spec=Candidate)
        candidate.id = "cand-1"
        candidate.name = "Test"
        candidate.skills = ["Python"]
        candidate.experience_years = 5
        candidate.current_title = "Engineer"
        candidate.current_company = "ACME"
        candidate.summary = "Good"

        application = Mock()
        application.id = "app-1"
        application.job_id = "job-1"
        application.match_score = Mock()

        job = Mock()
        job.title = "SWE"
        job.department = "Eng"
        job.requirements = "Python"

        from sqlalchemy import select

        async def execute_side_effect(query):
            mr = Mock()
            q = str(query).lower()
            if "candidates" in q:
                mr.scalar_one_or_none.return_value = candidate
            elif "applications" in q:
                mr.scalar_one_or_none.return_value = application
            elif "job_positions" in q or "jobposition" in q:
                mr.scalar_one_or_none.return_value = job
            return mr

        mock_db.execute = execute_side_effect

        svc = ReportService(mock_db)
        # Mock the LLM to return valid data
        with patch.object(svc, "_llm_generate") as mock_llm:
            mock_llm.return_value = {
                "score_dimensions": [],
                "overall_score": 80,
                "summary": "Good",
            }
            # Make setting match_score raise
            mock_db.commit.side_effect = [Exception("commit failed"), None]

            result = await svc.generate_report("cand-1", "app-1")
            assert mock_db.rollback.called
            assert result["llm_generated"] is True

    async def test_llm_generate_parses_response(self):
        mock_db = AsyncMock()
        svc = ReportService(mock_db)

        llm_mock = AsyncMock()
        llm_mock.chat.return_value = '{"score_dimensions": [], "overall_score": 85, "summary": "OK"}'
        svc._llm = llm_mock

        from app.models.candidate import Candidate

        candidate = Mock(spec=Candidate)
        candidate.name = "Test"
        candidate.skills = ["Python"]
        candidate.experience_years = 3
        candidate.current_title = "Dev"
        candidate.current_company = "Co"
        candidate.summary = "Fine"

        job = Mock()
        job.title = "Job"
        job.department = "Dep"
        job.requirements = "Req"

        result = await svc._llm_generate(candidate, job)
        assert result["overall_score"] == 85
        assert len(result["score_dimensions"]) == 0

    async def test_llm_generate_parses_fenced_json(self):
        mock_db = AsyncMock()
        svc = ReportService(mock_db)

        llm_mock = AsyncMock()
        llm_mock.chat.return_value = (
            "```json\n"
            '{"score_dimensions": [{"name": "专业", "score": 90, "reason": "OK"}], '
            '"overall_score": 90, "summary": "Great"}\n'
            "```"
        )
        svc._llm = llm_mock

        from app.models.candidate import Candidate

        candidate = Mock(spec=Candidate)
        candidate.name = "T"
        candidate.skills = []
        candidate.experience_years = 0
        candidate.current_title = ""
        candidate.current_company = ""
        candidate.summary = ""

        job = Mock()
        job.title = "Job"
        job.department = "Dep"
        job.requirements = "Req"

        result = await svc._llm_generate(candidate, job)
        assert result["overall_score"] == 90
