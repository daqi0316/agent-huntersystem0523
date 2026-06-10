"""Score taxonomy and evaluation schemas (P2-C Stage 10).

Defines the score types used across the recruitment agent system
and the result structure returned by evaluators.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ScoreType(StrEnum):
    """Score taxonomy for recruitment agent quality evaluation.

    Each entry maps to a measurable dimension of agent quality.
    Values follow the pattern `<domain>.<metric>` for consistency.
    """

    # ── Rule-based scores ──
    TOOL_SUCCESS = "tool.success"
    """Tool invocation completed without error (1.0) or failed (0.0)."""

    LATENCY = "latency"
    """Latency score: fast=1.0, within threshold=linear, slow=0.0."""

    PII_SAFETY = "pii.safety"
    """PII was properly masked (1.0) or leaked (0.0)."""

    INTENT_CORRECTNESS = "intent.correctness"
    """Agent correctly identified the user intent (1.0) or misclassified (0.0)."""

    # ── LLM judge scores ──
    RESUME_PARSE_QUALITY = "resume_parse.quality"
    """Quality of resume parsing output (LLM judge, 0.0-1.0)."""

    SCREENING_REASONABILITY = "screening.reasonability"
    """Screening decision is reasonable given the JD and resume (LLM judge, 0.0-1.0)."""

    JD_QUALITY = "jd.quality"
    """JD quality: clarity, completeness, fairness (LLM judge, 0.0-1.0)."""

    CONVERSATION_HELPFULNESS = "conversation.helpfulness"
    """Overall conversation helpfulness (LLM judge, 0.0-1.0)."""


@dataclass(slots=True)
class EvaluationResult:
    """Result from a single evaluator run.

    Attributes:
        score_name: ScoreType value or custom name.
        value: Score in [0.0, 1.0] range (1.0 = perfect).
        comment: Human-readable explanation.
        source: "rule", "llm_judge", or "human".
        evaluator_version: Version string for the evaluator.
        rubric_version: Version string for the rubric (LLM judge only).
        metadata: Additional context (e.g., thresholds used, LLM reasoning).
    """
    score_name: str
    value: float
    comment: str = ""
    source: str = "rule"
    evaluator_version: str = "1"
    rubric_version: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.value = max(0.0, min(1.0, self.value))
