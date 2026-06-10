"""ScoreWriter — 将评估结果写入 AgentOps provider。

通过已有的 ScoreEvent → provider.record_event 通道写入，
LangfuseExporter 自动将 ScoreEvent 导出为 Langfuse score。
"""
from __future__ import annotations

import logging
from typing import Any

from app.agentops.core.context import get_context
from app.agentops.core.schemas import EventType, ScoreEvent
from app.agentops.evaluation.schemas import EvaluationResult
from app.agentops.runtime import get_agentops_provider

logger = logging.getLogger(__name__)


class ScoreWriter:
    """Writes evaluation results as ScoreEvents to the active AgentOps provider.

    Usage:
        writer = ScoreWriter(trace_id="...")
        result = EvaluationResult(score_name="tool.success", value=1.0)
        await writer.write(result)
    """

    def __init__(
        self,
        trace_id: str = "",
        *,
        span_id: str = "",
        evaluator_version: str = "1",
    ) -> None:
        self._trace_id = trace_id
        self._span_id = span_id
        self._evaluator_version = evaluator_version
        self._provider = get_agentops_provider()

    @classmethod
    def from_context(cls, *, evaluator_version: str = "1") -> ScoreWriter:
        """Create writer from the current AgentOps context (trace_id + span_id)."""
        ctx = get_context()
        return cls(
            trace_id=ctx.trace_id if ctx else "",
            span_id=ctx.span_id if ctx else "",
            evaluator_version=evaluator_version,
        )

    async def write(self, result: EvaluationResult, **overrides: Any) -> None:
        """Write a single evaluation result as ScoreEvent.

        Args:
            result: The evaluation result to write.
            **overrides: Override any field on ScoreEvent (e.g., trace_id=...).
        """
        event = ScoreEvent(
            name=result.score_name,
            event_type=EventType.EVAL_SCORE_CREATED,
            trace_id=overrides.get("trace_id") or self._trace_id,
            span_id=overrides.get("span_id") or self._span_id,
            score_name=result.score_name,
            value=result.value,
            comment=result.comment,
            source=result.source,
            evaluator_version=result.evaluator_version or self._evaluator_version,
            rubric_version=result.rubric_version,
            metadata=result.metadata,
        )
        try:
            await self._provider.record_event(event)
        except Exception as exc:
            logger.debug("ScoreWriter.write failed (non-blocking): %s", exc)

    async def write_many(self, results: list[EvaluationResult], **overrides: Any) -> None:
        """Write multiple evaluation results in sequence."""
        for r in results:
            await self.write(r, **overrides)
