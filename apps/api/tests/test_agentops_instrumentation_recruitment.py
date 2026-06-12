"""Tests for RecruitmentEvents (P2-C Stage 9).

Covers:
- All 5 emitter methods emit with correct parameters
- Error isolation (emitter failure doesn't propagate)
- Event type selection (completed vs failed)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agentops.events.schemas import BusinessEventType
from app.agentops.instrumentation.recruitment import RecruitmentEvents


def _mock_emitter():
    """Create a mock emitter and patch get_event_emitter to return it."""
    emitter = AsyncMock()
    patcher = patch("app.agentops.instrumentation.recruitment.get_event_emitter", return_value=emitter)
    return emitter, patcher


class TestOnResumeParsed:
    async def test_emits_completed_event(self) -> None:
        emitter, patcher = _mock_emitter()
        with patcher:
            await RecruitmentEvents.on_resume_parsed(
                candidate_id="c1", quality_score=85, confidence=0.9,
                red_flags=["gap"],
            )
        emitter.emit.assert_awaited_once()
        args = emitter.emit.await_args[1]
        assert args["event_type"] == BusinessEventType.RESUME_PARSING_COMPLETED
        assert args["entity_id"] == "c1"
        assert args["domain_fields"]["quality_score"] == 85
        assert args["domain_fields"]["red_flags"] == ["gap"]

    async def test_emits_failed_on_error(self) -> None:
        emitter, patcher = _mock_emitter()
        with patcher:
            await RecruitmentEvents.on_resume_parsed(
                candidate_id="c1", quality_score=0, confidence=0,
                error="parse failed",
            )
        args = emitter.emit.await_args[1]
        assert args["event_type"] == BusinessEventType.RESUME_PARSING_FAILED

    async def test_is_non_blocking(self) -> None:
        """emitter.emit 抛异常 → 业务不中断。"""
        emitter, patcher = _mock_emitter()
        emitter.emit.side_effect = RuntimeError("boom")
        with patcher:
            await RecruitmentEvents.on_resume_parsed(
                candidate_id="c1", quality_score=85, confidence=0.9,
            )  # 不抛异常


class TestOnScreeningCompleted:
    async def test_emits_screening_event(self) -> None:
        emitter, patcher = _mock_emitter()
        with patcher:
            await RecruitmentEvents.on_screening_completed(
                candidate_id="c1", job_id="j1", match_score=0.85,
                decision="advance",
            )
        args = emitter.emit.await_args[1]
        assert args["event_type"] == BusinessEventType.SCREENING_COMPLETED
        assert args["entity_id"] == "c1"
        assert args["domain_fields"]["match_score"] == 0.85
        assert args["domain_fields"]["decision"] == "advance"

    async def test_includes_dimension_scores(self) -> None:
        emitter, patcher = _mock_emitter()
        with patcher:
            await RecruitmentEvents.on_screening_completed(
                candidate_id="c1", job_id="j1", match_score=0.85,
                decision="advance",
                dimension_scores={"technical": 0.9, "culture": 0.8},
            )
        args = emitter.emit.await_args[1]
        assert "dimension_scores" in args["domain_fields"]
        assert args["domain_fields"]["dimension_scores"]["technical"] == 0.9


class TestOnJDGenerated:
    async def test_emits_jd_event(self) -> None:
        emitter, patcher = _mock_emitter()
        with patcher:
            await RecruitmentEvents.on_jd_generated(
                job_id="j1", iteration_count=3, final_score=8.5,
                passed_threshold=True,
            )
        args = emitter.emit.await_args[1]
        assert args["event_type"] == BusinessEventType.JD_GENERATION_COMPLETED
        assert args["entity_type"] == "job"
        assert args["entity_id"] == "j1"
        assert args["domain_fields"]["iteration_count"] == 3

    async def test_emits_failed_on_error(self) -> None:
        emitter, patcher = _mock_emitter()
        with patcher:
            await RecruitmentEvents.on_jd_generated(
                job_id="j1", error="LLM unavailable",
            )
        args = emitter.emit.await_args[1]
        assert args["event_type"] == BusinessEventType.JD_GENERATION_FAILED


class TestOnInterviewScheduled:
    async def test_emits_schedule_event(self) -> None:
        emitter, patcher = _mock_emitter()
        with patcher:
            await RecruitmentEvents.on_interview_scheduled(
                candidate_id="c1", job_id="j1", schedule_success=True,
            )
        args = emitter.emit.await_args[1]
        assert args["event_type"] == BusinessEventType.INTERVIEW_SCHEDULED
        assert args["domain_fields"]["schedule_success"] is True


class TestOnEvaluationCompleted:
    async def test_entity_is_experiment(self) -> None:
        """entity_type == 'experiment', entity_id == experiment_id。"""
        emitter, patcher = _mock_emitter()
        with patcher:
            await RecruitmentEvents.on_evaluation_completed(
                experiment_id="exp-1", run_id="run-1",
                evaluator_name="ToolSuccess", score=0.9,
            )
        args = emitter.emit.await_args[1]
        assert args["event_type"] == BusinessEventType.EVALUATION_COMPLETED
        assert args["entity_type"] == "experiment"
        assert args["entity_id"] == "exp-1"
        assert args["domain_fields"]["evaluator"] == "ToolSuccess"


class TestPIIStrip:
    async def test_pii_not_in_domain(self) -> None:
        """姓名、邮箱等 PII 字段不应出现在 domain_fields 中。"""
        emitter, patcher = _mock_emitter()
        with patcher:
            await RecruitmentEvents.on_resume_parsed(
                candidate_id="c1", quality_score=85, confidence=0.9,
            )
        args = emitter.emit.await_args[1]
        for pii_key in ("name", "email", "phone", "address"):
            assert pii_key not in args["domain_fields"], f"{pii_key} should not be in domain_fields"
