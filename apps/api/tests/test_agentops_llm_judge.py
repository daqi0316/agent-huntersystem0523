"""Tests for LLM Judge engine (P2-C Stage 10/12 增强)."""
from __future__ import annotations

import pytest

from app.agentops.core.schemas import (
    EventType,
    LLMGenerationEvent,
)
from app.agentops.evaluation import (
    ConversationHelpfulnessEvaluator,
    HeuristicJudge,
    JDQualityEvaluator,
    MockJudge,
    PromptBasedJudge,
    ResumeParseQualityEvaluator,
    ScreeningReasonabilityEvaluator,
    get_rubric,
    register_rubric,
)
from app.agentops.evaluation.llm_judge import _extract_overall, _parse_score_json


# ════════════════════════════════════════════════════════════
# _parse_score_json / _extract_overall
# ════════════════════════════════════════════════════════════


class TestParseScore:
    def test_parse_valid_json(self) -> None:
        raw = '{"overall": 0.85, "reasoning": "good"}'
        parsed = _parse_score_json(raw)
        assert parsed is not None
        assert parsed["overall"] == 0.85

    def test_parse_json_in_code_block(self) -> None:
        raw = 'Some text\n```json\n{"overall": 0.9}\n```'
        parsed = _parse_score_json(raw)
        assert parsed is not None
        assert parsed["overall"] == 0.9

    def test_parse_malformed_returns_none(self) -> None:
        raw = "This is not JSON"
        assert _parse_score_json(raw) is None

    def test_extract_overall_direct(self) -> None:
        assert _extract_overall({"overall": 0.85}) == 0.85

    def test_extract_overall_average(self) -> None:
        assert _extract_overall({"a": 1.0, "b": 0.5}) == 0.75

    def test_extract_overall_clamped(self) -> None:
        assert _extract_overall({"overall": 1.5}) == 1.0
        assert _extract_overall({"overall": -0.5}) == 0.0

    def test_extract_overall_empty(self) -> None:
        assert _extract_overall({}) == 0.5


# ════════════════════════════════════════════════════════════
# LLMJudgeBackend implementations
# ════════════════════════════════════════════════════════════


class TestMockJudge:
    async def test_returns_fixed_score(self) -> None:
        judge = MockJudge(fixed_overall=0.92)
        scores, reasoning = await judge.judge("rubric", "input", "output")
        assert scores["overall"] == 0.92
        assert "Mock" in reasoning


class TestHeuristicJudge:
    async def test_empty_output_zero(self) -> None:
        judge = HeuristicJudge()
        scores, _ = await judge.judge("rubric", "input", "")
        assert scores["overall"] == 0.0

    async def test_long_output_higher_score(self) -> None:
        judge = HeuristicJudge()
        scores, _ = await judge.judge("rubric", "input", "x" * 1000)
        assert scores["overall"] == 1.0  # 1000 >= 500

    async def test_short_output_lower_score(self) -> None:
        judge = HeuristicJudge()
        scores, _ = await judge.judge("rubric", "input", "hello")
        assert 0.0 < scores["overall"] < 0.1


class TestPromptBasedJudge:
    async def test_parses_llm_response(self) -> None:
        async def fake_judge(prompt: str) -> str:
            return '{"overall": 0.88, "reasoning": "Pretty good"}'

        judge = PromptBasedJudge(fake_judge)
        scores, reasoning = await judge.judge("{input_text} {output_text}", "in", "out")
        assert scores["overall"] == 0.88
        assert "Pretty good" in reasoning

    async def test_failed_llm_returns_fallback(self) -> None:
        async def broken_judge(prompt: str) -> str:
            raise RuntimeError("LLM down")

        judge = PromptBasedJudge(broken_judge)
        scores, reasoning = await judge.judge("{input_text} {output_text}", "in", "out")
        # LLM 报错后降级到 HeuristicJudge，基于输出长度打分
        assert scores["overall"] < 0.5  # "out" 只有 3 chars → 低分
        assert "heuristic" in reasoning.lower() or "length" in reasoning.lower()

    async def test_unparseable_response(self) -> None:
        async def bad_response(prompt: str) -> str:
            return "I think this is good."

        judge = PromptBasedJudge(bad_response)
        scores, reasoning = await judge.judge("{input_text} {output_text}", "in", "out")
        assert scores["overall"] == 0.5
        assert "Unparseable" in reasoning


# ════════════════════════════════════════════════════════════
# Evaluators with judge_backend
# ════════════════════════════════════════════════════════════


class TestResumeParseWithJudge:
    async def test_with_mock_judge(self) -> None:
        evaluator = ResumeParseQualityEvaluator(judge_backend=MockJudge(0.85))
        event = LLMGenerationEvent(
            name="resume_parse",
            event_type=EventType.LLM_GENERATION_COMPLETED,
            output={"name": "张三"},
            input={"resume_text": "..."},
        )
        results = await evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.85
        assert results[0].source == "llm_judge"

    async def test_without_judge_falls_back_to_heuristic(self) -> None:
        evaluator = ResumeParseQualityEvaluator()
        event = LLMGenerationEvent(
            name="resume_parse",
            event_type=EventType.LLM_GENERATION_COMPLETED,
            output={"name": "张三"},
        )
        results = await evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].source == "rule"


class TestScreeningWithJudge:
    async def test_with_mock_judge(self) -> None:
        evaluator = ScreeningReasonabilityEvaluator(judge_backend=MockJudge(0.75))
        event = LLMGenerationEvent(
            name="screening",
            event_type=EventType.LLM_GENERATION_COMPLETED,
            output={"decision": "advance"},
        )
        results = await evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.75
        assert results[0].source == "llm_judge"

    async def test_without_judge_returns_default(self) -> None:
        evaluator = ScreeningReasonabilityEvaluator()
        event = LLMGenerationEvent(
            name="screening",
            event_type=EventType.LLM_GENERATION_COMPLETED,
        )
        results = await evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.5


class TestJDQualityWithJudge:
    async def test_with_mock_judge(self) -> None:
        evaluator = JDQualityEvaluator(judge_backend=MockJudge(0.9))
        event = LLMGenerationEvent(
            name="jd_generation",
            event_type=EventType.LLM_GENERATION_COMPLETED,
            output={"title": "Software Engineer"},
        )
        results = await evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.9

    async def test_without_judge_returns_default(self) -> None:
        evaluator = JDQualityEvaluator()
        event = LLMGenerationEvent(name="jd_generation", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.5


class TestConversationWithJudge:
    async def test_with_mock_judge(self) -> None:
        evaluator = ConversationHelpfulnessEvaluator(judge_backend=MockJudge(0.6))
        event = LLMGenerationEvent(
            name="final_response",
            event_type=EventType.LLM_GENERATION_COMPLETED,
        )
        results = await evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.6

    async def test_without_judge_returns_default(self) -> None:
        evaluator = ConversationHelpfulnessEvaluator()
        event = LLMGenerationEvent(name="final_response", event_type=EventType.LLM_GENERATION_COMPLETED)
        results = await evaluator.evaluate(event)
        assert len(results) == 1
        assert results[0].value == 0.5


# ════════════════════════════════════════════════════════════
# Rubric registry
# ════════════════════════════════════════════════════════════


class TestRubricRegistry:
    def test_get_rubric_known_types(self) -> None:
        assert "简历解析" in get_rubric("resume_parse.quality")
        assert "筛选决策" in get_rubric("screening.reasonability")
        assert "职位描述" in get_rubric("jd.quality")
        assert "客服对话" in get_rubric("conversation.helpfulness")

    def test_get_rubric_unknown_returns_empty(self) -> None:
        assert get_rubric("nonexistent") == ""

    def test_register_rubric(self) -> None:
        register_rubric("custom.test", "Custom rubric {input_text}")
        assert "Custom rubric" in get_rubric("custom.test")
