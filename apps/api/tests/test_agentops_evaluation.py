"""Tests for AgentOps Evaluation module (P2-C Stage 10).

Covers:
- ScoreType taxonomy
- EvaluationResult value clamping
- ScoreWriter creation and write
- All 4 rule-based evaluators (ToolSuccess, Latency, PII Safety, Intent Correctness)
- LLM judge evaluators (scaffolding)
- run_all_evaluators aggregation
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agentops.core.schemas import (
    BaseEvent,
    EventType,
    LLMGenerationEvent,
    ScoreEvent,
    SpanEvent,
    ToolInvocationEvent,
)
from app.agentops.evaluation import (
    BaseEvaluator,
    ConversationHelpfulnessEvaluator,
    EvaluationResult,
    IntentCorrectnessEvaluator,
    JDQualityEvaluator,
    LatencyEvaluator,
    PIISafetyEvaluator,
    ResumeParseQualityEvaluator,
    ScoreType,
    ScoreWriter,
    ScreeningReasonabilityEvaluator,
    ToolSuccessEvaluator,
    run_all_evaluators,
)


# ════════════════════════════════════════════════════════════
# ScoreType taxonomy
# ════════════════════════════════════════════════════════════


class TestScoreType:
    def test_all_taxonomy_values_are_unique(self) -> None:
        values = [st.value for st in ScoreType]
        assert len(values) == len(set(values)), "Duplicate score type values"

    def test_rule_based_types(self) -> None:
        assert ScoreType.TOOL_SUCCESS == "tool.success"
        assert ScoreType.LATENCY == "latency"
        assert ScoreType.PII_SAFETY == "pii.safety"
        assert ScoreType.INTENT_CORRECTNESS == "intent.correctness"

    def test_llm_judge_types(self) -> None:
        assert ScoreType.RESUME_PARSE_QUALITY == "resume_parse.quality"
        assert ScoreType.SCREENING_REASONABILITY == "screening.reasonability"
        assert ScoreType.JD_QUALITY == "jd.quality"
        assert ScoreType.CONVERSATION_HELPFULNESS == "conversation.helpfulness"


# ════════════════════════════════════════════════════════════
# EvaluationResult
# ════════════════════════════════════════════════════════════


class TestEvaluationResult:
    def test_value_clamped_to_0(self) -> None:
        r = EvaluationResult(score_name="test", value=-0.5)
        assert r.value == 0.0

    def test_value_clamped_to_1(self) -> None:
        r = EvaluationResult(score_name="test", value=1.5)
        assert r.value == 1.0

    def test_value_kept_in_range(self) -> None:
        r = EvaluationResult(score_name="test", value=0.75)
        assert r.value == 0.75

    def test_defaults(self) -> None:
        r = EvaluationResult(score_name="tool.success", value=1.0)
        assert r.source == "rule"
        assert r.evaluator_version == "1"
        assert r.rubric_version == ""
        assert r.metadata == {}


# ════════════════════════════════════════════════════════════
# ScoreWriter
# ════════════════════════════════════════════════════════════


class TestScoreWriter:
    async def test_write_creates_score_event(self) -> None:
        provider = AsyncMock()
        writer = ScoreWriter(trace_id="trace-1")
        writer._provider = provider

        result = EvaluationResult(score_name="tool.success", value=1.0, comment="OK")
        await writer.write(result)

        provider.record_event.assert_awaited_once()
        event = provider.record_event.await_args[0][0]
        assert isinstance(event, ScoreEvent)
        assert event.score_name == "tool.success"
        assert event.value == 1.0
        assert event.trace_id == "trace-1"

    async def test_write_many(self) -> None:
        provider = AsyncMock()
        writer = ScoreWriter(trace_id="trace-2")
        writer._provider = provider

        results = [
            EvaluationResult(score_name="a", value=1.0),
            EvaluationResult(score_name="b", value=0.5),
        ]
        await writer.write_many(results)

        assert provider.record_event.await_count == 2

    async def test_write_with_overrides(self) -> None:
        provider = AsyncMock()
        writer = ScoreWriter(trace_id="default-trace")
        writer._provider = provider

        result = EvaluationResult(score_name="test", value=0.8)
        await writer.write(result, trace_id="override-trace")

        event = provider.record_event.await_args[0][0]
        assert event.trace_id == "override-trace"

    async def test_write_failure_is_non_blocking(self) -> None:
        provider = AsyncMock()
        provider.record_event.side_effect = RuntimeError("provider down")
        writer = ScoreWriter(trace_id="trace-3")
        writer._provider = provider

        result = EvaluationResult(score_name="test", value=1.0)
        # Should not raise
        await writer.write(result)

    async def test_from_context_without_context_creates_empty(self) -> None:
        writer = ScoreWriter.from_context()
        assert writer._trace_id == ""


# ════════════════════════════════════════════════════════════
# ToolSuccessEvaluator
# ════════════════════════════════════════════════════════════


class TestToolSuccessEvaluator:
    evaluator = ToolSuccessEvaluator()

    async def test_completed_tool_returns_1(self) -> None:
        event = ToolInvocationEvent(
            name="test_tool",
            event_type=EventType.TOOL_INVOCATION_COMPLETED,
            tool_name="parse_resume",
            tool_category="resume_parser",
            success=True,
        )
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 1.0
        assert results[0].score_name == ScoreType.TOOL_SUCCESS

    async def test_failed_tool_returns_0(self) -> None:
        event = ToolInvocationEvent(
            name="test_tool",
            event_type=EventType.TOOL_INVOCATION_FAILED,
            tool_name="parse_resume",
            tool_category="resume_parser",
            success=False,
            error="connection refused",
        )
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.0

    async def test_irrelevant_event_returns_empty(self) -> None:
        event = SpanEvent(name="test", event_type=EventType.SPAN_STARTED)
        results = await self.evaluator.evaluate(event)
        assert results == []


# ════════════════════════════════════════════════════════════
# LatencyEvaluator
# ════════════════════════════════════════════════════════════


class TestLatencyEvaluator:
    evaluator = LatencyEvaluator()

    async def test_fast_latency_returns_1(self) -> None:
        event = SpanEvent(name="fast", event_type=EventType.SPAN_COMPLETED, duration_ms=100.0)
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 1.0

    async def test_slow_latency_returns_0(self) -> None:
        event = SpanEvent(name="slow", event_type=EventType.SPAN_COMPLETED, duration_ms=6000.0)
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.0

    async def test_medium_latency_interpolates(self) -> None:
        event = SpanEvent(name="medium", event_type=EventType.SPAN_COMPLETED, duration_ms=3000.0)
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert 0.0 < results[0].value < 1.0

    async def test_no_duration_returns_empty(self) -> None:
        event = SpanEvent(name="no_dur", event_type=EventType.SPAN_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert results == []


# ════════════════════════════════════════════════════════════
# PIISafetyEvaluator
# ════════════════════════════════════════════════════════════


class TestPIISafetyEvaluator:
    evaluator = PIISafetyEvaluator()

    async def test_redaction_applied_returns_1(self) -> None:
        event = BaseEvent(name="redact", event_type=EventType.PRIVACY_REDACTION_APPLIED)
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 1.0
        assert results[0].score_name == ScoreType.PII_SAFETY

    async def test_other_event_returns_empty(self) -> None:
        event = SpanEvent(name="other", event_type=EventType.SPAN_STARTED)
        results = await self.evaluator.evaluate(event)
        assert results == []


# ════════════════════════════════════════════════════════════
# IntentCorrectnessEvaluator
# ════════════════════════════════════════════════════════════


class TestIntentCorrectnessEvaluator:
    evaluator = IntentCorrectnessEvaluator()

    async def test_intent_span_with_output_returns_1(self) -> None:
        event = SpanEvent(
            name="intent_recognition",
            event_type=EventType.SPAN_COMPLETED,
            output={"intent": "screening", "confidence": 0.9},
        )
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 1.0

    async def test_intent_span_without_output_returns_0(self) -> None:
        event = SpanEvent(name="intent_recognition", event_type=EventType.SPAN_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.0

    async def test_non_intent_span_returns_empty(self) -> None:
        event = SpanEvent(name="tool_execution", event_type=EventType.SPAN_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert results == []


# ════════════════════════════════════════════════════════════
# ResumeParseQualityEvaluator
# ════════════════════════════════════════════════════════════


class TestResumeParseQualityEvaluator:
    evaluator = ResumeParseQualityEvaluator()

    async def test_resume_llm_with_complete_output(self) -> None:
        event = LLMGenerationEvent(
            name="resume_parse",
            event_type=EventType.LLM_GENERATION_COMPLETED,
            output={
                "name": "张三",
                "email": "z@t.com",
                "skills": ["Python", "FastAPI"],
                "experience_years": 5,
                "education": "本科",
                "current_company": "Acme",
            },
        )
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value > 0.9  # all fields present
        assert results[0].score_name == ScoreType.RESUME_PARSE_QUALITY

    async def test_resume_llm_with_partial_output(self) -> None:
        event = LLMGenerationEvent(
            name="resume_parse",
            event_type=EventType.LLM_GENERATION_COMPLETED,
            output={"name": "张三"},
        )
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value < 1.0

    async def test_non_resume_event_returns_empty(self) -> None:
        event = LLMGenerationEvent(name="other", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert results == []


# ════════════════════════════════════════════════════════════
# ScreeningReasonabilityEvaluator
# ════════════════════════════════════════════════════════════


class TestScreeningReasonabilityEvaluator:
    evaluator = ScreeningReasonabilityEvaluator()

    async def test_screening_event_returns_default(self) -> None:
        event = LLMGenerationEvent(name="screening", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.5

    async def test_non_screening_event_returns_empty(self) -> None:
        event = LLMGenerationEvent(name="other", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert results == []


# ════════════════════════════════════════════════════════════
# JDQualityEvaluator
# ════════════════════════════════════════════════════════════


class TestJDQualityEvaluator:
    evaluator = JDQualityEvaluator()

    async def test_jd_event_returns_default(self) -> None:
        event = LLMGenerationEvent(name="jd_generation", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1

    async def test_non_jd_event_returns_empty(self) -> None:
        event = LLMGenerationEvent(name="other", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert results == []


# ════════════════════════════════════════════════════════════
# ConversationHelpfulnessEvaluator
# ════════════════════════════════════════════════════════════


class TestConversationHelpfulnessEvaluator:
    evaluator = ConversationHelpfulnessEvaluator()

    async def test_response_event_returns_default(self) -> None:
        event = LLMGenerationEvent(name="final_response", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1

    async def test_helpfulness_event_returns_default(self) -> None:
        event = LLMGenerationEvent(name="helpful_response", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert len(results) == 1

    async def test_unrelated_event_returns_empty(self) -> None:
        event = LLMGenerationEvent(name="tool_call", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await self.evaluator.evaluate(event)
        assert results == []

    async def test_not_completed_returns_empty(self) -> None:
        event = LLMGenerationEvent(name="final_response", event_type=EventType.LLM_GENERATION_STARTED)
        results = await self.evaluator.evaluate(event)
        assert results == []


# ════════════════════════════════════════════════════════════
# run_all_evaluators
# ════════════════════════════════════════════════════════════


class TestRunAllEvaluators:
    async def test_runs_all_evaluators_on_events(self) -> None:
        events = [
            ToolInvocationEvent(name="t1", event_type=EventType.TOOL_INVOCATION_COMPLETED, tool_name="parse", tool_category="resume"),
            SpanEvent(name="s1", event_type=EventType.SPAN_COMPLETED, duration_ms=100.0),
        ]
        results = await run_all_evaluators(events)
        # At least ToolSuccess (1) + Latency (1) should match
        assert len(results) >= 2

    async def test_empty_events_returns_empty(self) -> None:
        results = await run_all_evaluators([])
        assert results == []

    async def test_evaluator_error_is_non_blocking(self) -> None:
        class BrokenEvaluator(BaseEvaluator):
            async def evaluate(self, event):  # type: ignore[no-untyped-def]
                raise RuntimeError("boom")

        events = [SpanEvent(name="test", event_type=EventType.SPAN_COMPLETED)]
        results = await run_all_evaluators(events, evaluators=[BrokenEvaluator()])
        assert results == []
