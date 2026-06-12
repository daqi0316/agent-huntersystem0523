"""CostRecordingProvider — 拦截 LLM 生成事件，持久化写入 DB。

作为 AgentOpsProvider 链中的一环，在 record_generation 被调用时将
LLMGenerationEvent 写入 agent_llm_generations 表。

设计原则:
- 非阻塞：DB 写入失败不影响 LLM 调用链路
- 只关注 COMPLETED / FAILED 事件（STARTED 没有 token 数据）
- 写入时计算成本，查询时零计算
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agentops.core.schemas import (
    BaseEvent,
    EventType,
    LLMGenerationEvent,
    ScoreEvent,
    SpanEvent,
    ToolInvocationEvent,
    TraceEvent,
)
from app.agentops.cost.pricing import calculate_cost

logger = logging.getLogger(__name__)

# 内容预告截断长度
_PREVIEW_MAX_CHARS = 500


class CostRecordingProvider:
    """AgentOps provider 实现 — 将 LLM 生成事件持久化到 DB。

    使用方式（由 runtime.py 自动注入 CompositeProvider 链）:
        provider = CompositeProvider(providers=[
            ExportProvider(queue=queue),
            CostRecordingProvider(),         # ← 追加此 provider
        ])
    """

    async def record_event(self, event: BaseEvent) -> None:
        _ = event
        return None

    async def start_trace(self, event: TraceEvent) -> None:
        _ = event
        return None

    async def start_span(self, event: SpanEvent) -> None:
        _ = event
        return None

    async def record_generation(self, event: LLMGenerationEvent) -> None:
        """只处理 COMPLETED 和 FAILED 事件（STARTED 还没有 token 数据）。"""
        if event.event_type == EventType.LLM_GENERATION_STARTED:
            return

        try:
            await self._persist(event)
        except Exception as exc:
            # 非阻塞：记录成本不应打断 LLM 调用
            logger.warning("cost recording failed (non-blocking): %s", exc, exc_info=True)

    async def record_tool_call(self, event: ToolInvocationEvent) -> None:
        _ = event
        return None

    async def record_score(self, event: ScoreEvent) -> None:
        _ = event
        return None

    async def flush(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _persist(self, event: LLMGenerationEvent) -> None:
        """将事件写入 DB。"""
        from app.agentops.cost.models import LLMGenerationRecord
        from app.core.database import AsyncSessionLocal

        cost = calculate_cost(
            model=event.model,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
        )

        input_preview = self._truncate_preview(event.input)
        output_preview = self._truncate_preview(event.output)
        metadata = self._extract_metadata(event)

        record = LLMGenerationRecord(
            id=event.event_id,
            trace_id=event.trace_id,
            span_id=event.span_id,
            user_id=event.user_id,
            session_id=event.session_id,
            tenant_id=event.tenant_id,
            provider=event.provider,
            model=event.model,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            total_tokens=event.total_tokens,
            duration_ms=event.duration_ms,
            estimated_cost=cost,
            cost_currency="USD",
            input_preview=input_preview,
            output_preview=output_preview,
            error=event.error or None,
            metadata_json=metadata,
        )

        async with AsyncSessionLocal() as session:
            session.add(record)
            await session.commit()

    @staticmethod
    def _truncate_preview(value: Any) -> str | None:
        """将 input/output 截断为可读摘要。"""
        if value is None:
            return None
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
        if len(text) > _PREVIEW_MAX_CHARS:
            text = text[:_PREVIEW_MAX_CHARS] + "..."
        return text

    @staticmethod
    def _extract_metadata(event: LLMGenerationEvent) -> dict[str, Any] | None:
        """提取事件的 metadata 和 parameters。"""
        meta: dict[str, Any] = {}
        if event.parameters:
            meta["parameters"] = event.parameters
        if event.tags:
            meta["tags"] = event.tags
        if event.metadata:
            meta.update(event.metadata)
        return meta if meta else None
