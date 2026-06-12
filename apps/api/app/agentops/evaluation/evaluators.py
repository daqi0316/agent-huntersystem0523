"""Evaluators — 规则评估器与 LLM judge 评估器 (P2-C Stage 10).

实现 §19.10 中定义的 8 种评估器:
- 4 个 rule-based (ToolSuccess, Latency, PII Safety, Intent Correctness)
- 4 个 LLM judge (ResumeParse, Screening, JD, Conversation)

设计原则:
- 每个评估器只关注一个维度
- 评估器接收 BaseEvent, 返回 EvaluationResult 列表
- rule-based 评估器无副作用, LLM judge 评估器调 LLM
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.agentops.core.schemas import (
    BaseEvent,
    EventType,
    LLMGenerationEvent,
    SpanEvent,
    ToolInvocationEvent,
)
from app.agentops.evaluation.llm_judge import (
    LLMJudgeBackend,
    _extract_overall,
    get_rubric,
)
from app.agentops.evaluation.schemas import EvaluationResult, ScoreType

logger = logging.getLogger(__name__)


def _dict_or_json(value: object) -> str:
    """将 dict 或任意值转为 JSON 字符串，供 LLM judge 消费。"""
    if value is None:
        return ""
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, str):
        return value
    return str(value)

# ── 阈值常量 ──
LATENCY_THRESHOLD_MS: float = 5000.0  # 5s 以上视为慢
LATENCY_PERFECT_MS: float = 1000.0   # 1s 以内满分
TOOL_SUCCESS_VALUE: float = 1.0
TOOL_FAILURE_VALUE: float = 0.0


# ════════════════════════════════════════════════════════════
# Base
# ════════════════════════════════════════════════════════════


class BaseEvaluator(ABC):
    """Base class for all evaluators.

    Subclasses implement `evaluate(event)` and declare `version`.
    """

    version: str = "1"

    @abstractmethod
    async def evaluate(self, event: BaseEvent) -> list[EvaluationResult]:
        """Evaluate an event and return scores.

        Returns an empty list if the event type is not applicable.
        """
        ...


# ════════════════════════════════════════════════════════════
# Rule-based evaluators
# ════════════════════════════════════════════════════════════


class ToolSuccessEvaluator(BaseEvaluator):
    """Evaluates whether a tool invocation succeeded.

    Matches TOOL_INVOCATION_COMPLETED / TOOL_INVOCATION_FAILED events.
    Success → 1.0, Failure → 0.0.
    """

    version = "1"

    async def evaluate(self, event: BaseEvent) -> list[EvaluationResult]:
        if not isinstance(event, ToolInvocationEvent):
            return []
        if event.event_type == EventType.TOOL_INVOCATION_COMPLETED:
            return [
                EvaluationResult(
                    score_name=ScoreType.TOOL_SUCCESS,
                    value=TOOL_SUCCESS_VALUE,
                    comment=f"Tool {event.tool_name} completed successfully",
                    source="rule",
                    evaluator_version=self.version,
                    metadata={"tool_name": event.tool_name, "tool_category": event.tool_category},
                )
            ]
        if event.event_type == EventType.TOOL_INVOCATION_FAILED:
            return [
                EvaluationResult(
                    score_name=ScoreType.TOOL_SUCCESS,
                    value=TOOL_FAILURE_VALUE,
                    comment=f"Tool {event.tool_name} failed: {event.error[:200] if event.error else 'unknown'}",
                    source="rule",
                    evaluator_version=self.version,
                    metadata={
                        "tool_name": event.tool_name,
                        "error": event.error or "",
                    },
                )
            ]
        return []


class LatencyEvaluator(BaseEvaluator):
    """Evaluates latency performance.

    Works on any event with duration_ms.
    - duration <= PERFECT_MS → 1.0
    - duration >= THRESHOLD_MS → 0.0
    - linear interpolation in between.
    """

    version = "1"
    threshold_ms: float = LATENCY_THRESHOLD_MS
    perfect_ms: float = LATENCY_PERFECT_MS

    async def evaluate(self, event: BaseEvent) -> list[EvaluationResult]:
        duration_ms: float | None = getattr(event, "duration_ms", None)
        if duration_ms is None:
            return []

        event_name = event.name or event.event_type.value
        if duration_ms <= self.perfect_ms:
            value = 1.0
        elif duration_ms >= self.threshold_ms:
            value = 0.0
        else:
            # linear interpolation: 1.0 → 0.0 over [perfect_ms, threshold_ms]
            value = 1.0 - (duration_ms - self.perfect_ms) / (self.threshold_ms - self.perfect_ms)

        return [
            EvaluationResult(
                score_name=ScoreType.LATENCY,
                value=value,
                comment=f"Latency {duration_ms:.0f}ms (perfect<={self.perfect_ms:.0f}ms, threshold>={self.threshold_ms:.0f}ms)",
                source="rule",
                evaluator_version=self.version,
                metadata={
                    "duration_ms": f"{duration_ms:.1f}",
                    "perfect_ms": f"{self.perfect_ms:.0f}",
                    "threshold_ms": f"{self.threshold_ms:.0f}",
                },
            )
        ]


class PIISafetyEvaluator(BaseEvaluator):
    """Evaluates whether PII redaction was applied.

    Checks if a PRIVACY_REDACTION_APPLIED event exists in the trace.
    For simplicity, looks at event type directly.

    Note: In production, this should scan all events in a trace
    for unredacted PII patterns. Here we check the presence of
    privacy.redaction.applied events as a proxy.
    """

    version = "1"

    async def evaluate(self, event: BaseEvent) -> list[EvaluationResult]:
        if event.event_type == EventType.PRIVACY_REDACTION_APPLIED:
            return [
                EvaluationResult(
                    score_name=ScoreType.PII_SAFETY,
                    value=1.0,
                    comment="PII redaction was applied",
                    source="rule",
                    evaluator_version=self.version,
                )
            ]
        return []


class IntentCorrectnessEvaluator(BaseEvaluator):
    """Evaluates whether intent recognition produced a valid intent.

    Checks if a SPAN_COMPLETED event with name containing "intent"
    has a non-empty output. This is a lightweight heuristic.
    """

    version = "1"

    async def evaluate(self, event: BaseEvent) -> list[EvaluationResult]:
        if not isinstance(event, SpanEvent):
            return []
        if event.event_type != EventType.SPAN_COMPLETED:
            return []
        if "intent" not in (event.name or "").lower():
            return []

        output = event.output
        if output and isinstance(output, dict) and output.get("intent"):
            return [
                EvaluationResult(
                    score_name=ScoreType.INTENT_CORRECTNESS,
                    value=1.0,
                    comment=f"Intent recognized: {output.get('intent')}",
                    source="rule",
                    evaluator_version=self.version,
                    metadata={"intent": str(output.get("intent", ""))},
                )
            ]
        return [
            EvaluationResult(
                score_name=ScoreType.INTENT_CORRECTNESS,
                value=0.0,
                comment="Intent not recognized or empty",
                source="rule",
                evaluator_version=self.version,
            )
        ]


# ════════════════════════════════════════════════════════════
# LLM judge evaluators (scaffolding)
# ════════════════════════════════════════════════════════════


class ResumeParseQualityEvaluator(BaseEvaluator):
    """LLM judge — evaluates resume parsing quality.

    Two modes:
    1. LLM judge mode (judge_backend provided): uses rubric + LLM
    2. Heuristic mode (default): field-level completeness scoring
    """

    version = "1"

    def __init__(self, judge_backend: LLMJudgeBackend | None = None) -> None:
        self._judge_backend = judge_backend

    async def evaluate(self, event: BaseEvent) -> list[EvaluationResult]:
        if not isinstance(event, LLMGenerationEvent):
            return []
        if event.event_type != EventType.LLM_GENERATION_COMPLETED:
            return []
        if "resume" not in (event.name or "").lower():
            return []

        output = event.output
        if not output or not isinstance(output, dict):
            return []

        if self._judge_backend:
            return await self._evaluate_with_judge(event)
        return self._evaluate_heuristic(event, output)

    async def _evaluate_with_judge(self, event: LLMGenerationEvent) -> list[EvaluationResult]:
        input_text = _dict_or_json(event.input)
        output_text = _dict_or_json(event.output)
        scores, reasoning = await self._judge_backend.judge(
            get_rubric(ScoreType.RESUME_PARSE_QUALITY), input_text, output_text,
        )
        overall = _extract_overall(scores)
        return [
            EvaluationResult(
                score_name=ScoreType.RESUME_PARSE_QUALITY,
                value=overall,
                comment=reasoning or f"LLM judge: {overall:.2f}",
                source="llm_judge",
                evaluator_version=self.version,
                rubric_version="v1",
                metadata={"model": event.model, "dimensions": str(scores)},
            )
        ]

    def _evaluate_heuristic(self, event: LLMGenerationEvent, output: dict[str, Any]) -> list[EvaluationResult]:
        score = self._score_output(output)
        return [
            EvaluationResult(
                score_name=ScoreType.RESUME_PARSE_QUALITY,
                value=score,
                comment=f"Resume parse quality heuristic: {score:.2f}",
                source="rule",
                evaluator_version=self.version,
                metadata={
                    "model": event.model,
                    "prompt_tokens": str(event.prompt_tokens),
                    "completion_tokens": str(event.completion_tokens),
                },
            )
        ]

    @staticmethod
    def _score_output(output: dict[str, Any]) -> float:
        score = 0.0
        total = 0.0
        if output.get("name"):
            score += 0.15
        total += 0.15
        if output.get("email"):
            score += 0.15
        total += 0.15
        if output.get("skills"):
            if isinstance(output["skills"], list) and len(output["skills"]) > 0:
                score += 0.25
        total += 0.25
        if output.get("experience_years") is not None:
            score += 0.20
        total += 0.20
        if output.get("education"):
            score += 0.15
        total += 0.15
        if output.get("current_company") or output.get("current_title"):
            score += 0.10
        total += 0.10
        return score / total if total > 0 else 0.0


class ScreeningReasonabilityEvaluator(BaseEvaluator):
    """LLM judge — evaluates screening decision reasonability."""

    version = "1"

    def __init__(self, judge_backend: LLMJudgeBackend | None = None) -> None:
        self._judge_backend = judge_backend

    async def evaluate(self, event: BaseEvent) -> list[EvaluationResult]:
        if not isinstance(event, LLMGenerationEvent):
            return []
        if "screen" not in (event.name or "").lower():
            return []

        if self._judge_backend:
            input_text = _dict_or_json(event.input)
            output_text = _dict_or_json(event.output)
            scores, reasoning = await self._judge_backend.judge(
                get_rubric(ScoreType.SCREENING_REASONABILITY), input_text, output_text,
            )
            overall = _extract_overall(scores)
            return [
                EvaluationResult(
                    score_name=ScoreType.SCREENING_REASONABILITY,
                    value=overall,
                    comment=reasoning or f"LLM judge: {overall:.2f}",
                    source="llm_judge",
                    evaluator_version=self.version,
                    rubric_version="v1",
                )
            ]

        return [
            EvaluationResult(
                score_name=ScoreType.SCREENING_REASONABILITY,
                value=0.5,
                comment="No LLM judge backend; default score",
                source="rule",
                evaluator_version=self.version,
            )
        ]


class JDQualityEvaluator(BaseEvaluator):
    """LLM judge — evaluates JD generation quality."""

    version = "1"

    def __init__(self, judge_backend: LLMJudgeBackend | None = None) -> None:
        self._judge_backend = judge_backend

    async def evaluate(self, event: BaseEvent) -> list[EvaluationResult]:
        if not isinstance(event, LLMGenerationEvent):
            return []
        if "jd" not in (event.name or "").lower():
            return []

        if self._judge_backend:
            input_text = _dict_or_json(event.input)
            output_text = _dict_or_json(event.output)
            scores, reasoning = await self._judge_backend.judge(
                get_rubric(ScoreType.JD_QUALITY), input_text, output_text,
            )
            overall = _extract_overall(scores)
            return [
                EvaluationResult(
                    score_name=ScoreType.JD_QUALITY,
                    value=overall,
                    comment=reasoning or f"LLM judge: {overall:.2f}",
                    source="llm_judge",
                    evaluator_version=self.version,
                    rubric_version="v1",
                )
            ]

        return [
            EvaluationResult(
                score_name=ScoreType.JD_QUALITY,
                value=0.5,
                comment="No LLM judge backend; default score",
                source="rule",
                evaluator_version=self.version,
            )
        ]


class ConversationHelpfulnessEvaluator(BaseEvaluator):
    """LLM judge — evaluates overall conversation helpfulness."""

    version = "1"

    def __init__(self, judge_backend: LLMJudgeBackend | None = None) -> None:
        self._judge_backend = judge_backend

    async def evaluate(self, event: BaseEvent) -> list[EvaluationResult]:
        if not isinstance(event, LLMGenerationEvent):
            return []
        if event.event_type != EventType.LLM_GENERATION_COMPLETED:
            return []
        if "helpful" not in (event.name or "").lower() and "response" not in (event.name or "").lower():
            return []

        if self._judge_backend:
            input_text = _dict_or_json(event.input)
            output_text = _dict_or_json(event.output)
            scores, reasoning = await self._judge_backend.judge(
                get_rubric(ScoreType.CONVERSATION_HELPFULNESS), input_text, output_text,
            )
            overall = _extract_overall(scores)
            return [
                EvaluationResult(
                    score_name=ScoreType.CONVERSATION_HELPFULNESS,
                    value=overall,
                    comment=reasoning or f"LLM judge: {overall:.2f}",
                    source="llm_judge",
                    evaluator_version=self.version,
                    rubric_version="v1",
                )
            ]

        return [
            EvaluationResult(
                score_name=ScoreType.CONVERSATION_HELPFULNESS,
                value=0.5,
                comment="No LLM judge backend; default score",
                source="rule",
                evaluator_version=self.version,
            )
        ]


# ════════════════════════════════════════════════════════════
# 聚合运行
# ════════════════════════════════════════════════════════════

_DEFAULT_EVALUATORS: list[BaseEvaluator] = [
    ToolSuccessEvaluator(),
    LatencyEvaluator(),
    PIISafetyEvaluator(),
    IntentCorrectnessEvaluator(),
    ResumeParseQualityEvaluator(),
    ScreeningReasonabilityEvaluator(),
    JDQualityEvaluator(),
    ConversationHelpfulnessEvaluator(),
]


async def run_all_evaluators(
    events: list[BaseEvent],
    evaluators: list[BaseEvaluator] | None = None,
) -> list[EvaluationResult]:
    """Run all evaluators against a list of events.

    Args:
        events: List of BaseEvent instances (trace/span/tool/LLM).
        evaluators: Evaluator instances; defaults to all.

    Returns:
        Flattened list of EvaluationResult from all evaluators.
    """
    results: list[EvaluationResult] = []
    eval_instances = evaluators or _DEFAULT_EVALUATORS
    for evaluator in eval_instances:
        for event in events:
            try:
                scores = await evaluator.evaluate(event)
                results.extend(scores)
            except Exception as exc:
                logger.debug("Evaluator %s failed on event %s: %s", type(evaluator).__name__, event.event_type, exc)
    return results
