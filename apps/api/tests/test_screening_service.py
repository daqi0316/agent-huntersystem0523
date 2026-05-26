"""Screening service tests: pipeline orchestration, evaluations, status transitions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestScreeningServiceUnit:
    """Unit tests for ScreeningService."""

    @pytest.mark.asyncio
    async def test_aggregator_property_lazy_init(self):
        """Aggregator property creates instance on first access."""
        from app.services.screening import ScreeningService

        service = ScreeningService()
        assert service._aggregator is None

        agg = service.aggregator
        assert agg is not None
        assert service._aggregator is agg
        assert agg.name == "candidate_evaluator"

    @pytest.mark.asyncio
    async def test_aggregator_property_cached(self):
        """Aggregator property returns cached instance."""
        from app.services.screening import ScreeningService

        service = ScreeningService()
        agg1 = service.aggregator
        agg2 = service.aggregator

        assert agg1 is agg2

    @pytest.mark.asyncio
    async def test_pipeline_property_lazy_init(self):
        """Pipeline property creates instance on first access."""
        from app.services.screening import ScreeningService

        service = ScreeningService()
        assert service._pipeline is None

        p = service.pipeline
        assert p is not None
        assert service._pipeline is p

    @pytest.mark.asyncio
    async def test_pipeline_property_cached(self):
        """Pipeline property returns cached instance."""
        from app.services.screening import ScreeningService

        service = ScreeningService()
        p1 = service.pipeline
        p2 = service.pipeline

        assert p1 is p2

    @pytest.mark.asyncio
    async def test_get_pipeline_progress_returns_completed(self):
        """get_pipeline_progress returns completed status."""
        from app.services.screening import ScreeningService

        service = ScreeningService()
        result = await service.get_pipeline_progress("test-id-123")

        assert result["pipeline_id"] == "test-id-123"
        assert result["status"] == "completed"
        assert result["progress"] == 1.0
        assert result["current_step"] == "done"

    @pytest.mark.asyncio
    async def test_screen_resume_success(self):
        """screen_resume returns parsed result when pipeline succeeds."""
        from app.services.screening import ScreeningService

        mock_result = {
            "pipeline_id": "pipe-1",
            "final_output": {
                "parsed_resume": {"name": "Alice"},
                "match_result": {
                    "overall_score": 8.5,
                    "strengths": ["strong skills"],
                    "weaknesses": ["lack exp"],
                    "recommendation": "推荐",
                },
                "gate_result": {
                    "needs_human_review": False,
                    "gate_summary": "pass",
                },
                "gate_passed": True,
                "final_score": 8.5,
            },
            "steps": [{"name": "parse", "status": "done"}],
        }

        service = ScreeningService()
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=mock_result)
        service._pipeline = mock_pipeline

        result = await service.screen_resume(
            candidate_id="cand-1",
            job_id="job-1",
            resume_text="resume text",
            job_requirements="reqs",
        )

        assert result["pipeline_id"] == "pipe-1"
        assert result["candidate_id"] == "cand-1"
        assert result["overall_score"] == 8.5
        assert result["gate_passed"] is True
        assert result["needs_human_review"] is False
        assert len(result["steps"]) == 1
        mock_pipeline.run.assert_called_once_with(
            {"resume_text": "resume text", "job_requirements": "reqs"}
        )

    @pytest.mark.asyncio
    async def test_screen_resume_fallback_on_exception(self):
        """screen_resume returns fallback when pipeline raises."""
        from app.services.screening import ScreeningService

        service = ScreeningService()
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(side_effect=Exception("LLM unavailable"))
        service._pipeline = mock_pipeline

        result = await service.screen_resume(
            candidate_id="cand-2",
            job_id="job-2",
            resume_text="text",
            job_requirements="reqs",
        )

        assert result["overall_score"] == 0
        assert result["gate_passed"] is False
        assert result["needs_human_review"] is True
        assert "评估不可用" in result["recommendation"]

    @pytest.mark.asyncio
    async def test_start_screening_success(self):
        """start_screening updates status to EVALUATING."""
        from app.services.screening import ScreeningService

        mock_session = AsyncMock()
        service = ScreeningService()

        result = await service.start_screening(mock_session, "cand-1")
        assert result is True
        assert mock_session.execute.called
        assert mock_session.commit.called

    @pytest.mark.asyncio
    async def test_start_screening_failure(self):
        """start_screening returns False on DB error."""
        from app.services.screening import ScreeningService

        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB error")

        service = ScreeningService()
        result = await service.start_screening(mock_session, "cand-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_complete_screening_passed(self):
        """complete_screening with passed=True sets EVALUATED."""
        from app.services.screening import ScreeningService

        mock_session = AsyncMock()
        service = ScreeningService()

        result = await service.complete_screening(mock_session, "cand-1", passed=True)
        assert result is True

    @pytest.mark.asyncio
    async def test_complete_screening_failed(self):
        """complete_screening with passed=False sets FAILED."""
        from app.services.screening import ScreeningService

        mock_session = AsyncMock()
        service = ScreeningService()

        result = await service.complete_screening(mock_session, "cand-1", passed=False)
        assert result is True

    @pytest.mark.asyncio
    async def test_complete_screening_db_error(self):
        """complete_screening returns False on DB error."""
        from app.services.screening import ScreeningService

        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB error")

        service = ScreeningService()
        result = await service.complete_screening(mock_session, "cand-1", passed=True)
        assert result is False

    @pytest.mark.asyncio
    async def test_set_interviewing_success(self):
        """set_interviewing updates status to IN_INTERVIEW."""
        from app.services.screening import ScreeningService

        mock_session = AsyncMock()
        service = ScreeningService()

        result = await service.set_interviewing(mock_session, "cand-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_set_interviewing_failure(self):
        """set_interviewing returns False on DB error."""
        from app.services.screening import ScreeningService

        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB error")

        service = ScreeningService()
        result = await service.set_interviewing(mock_session, "cand-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_multi_evaluate_success(self):
        """multi_evaluate returns aggregator result on success."""
        from app.services.screening import ScreeningService

        mock_agg = MagicMock()
        mock_agg.run = AsyncMock(return_value={"evaluations": [], "summary": "done"})

        service = ScreeningService()
        service._aggregator = mock_agg

        result = await service.multi_evaluate("candidate info", ["skill"])
        assert "evaluations" in result
        mock_agg.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_evaluate_fallback(self):
        """multi_evaluate returns fallback on exception."""
        from app.services.screening import ScreeningService

        mock_agg = MagicMock()
        mock_agg.run = AsyncMock(side_effect=Exception("LLM error"))

        service = ScreeningService()
        service._aggregator = mock_agg

        result = await service.multi_evaluate("candidate info")
        assert "error" in result
        assert result["error"] == "Evaluation unavailable"
