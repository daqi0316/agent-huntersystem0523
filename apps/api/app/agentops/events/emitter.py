"""EventEmitter — 业务事件发射器。

职责:
  1. 从 AgentOpsContext 读取当前 trace_id / span_id / user_id / session_id
  2. 构造 BusinessEvent
  3. 通过 CompositeProvider 记录（转发到 Langfuse / 队列）
  4. 同步导出关键指标为 ScoreEvent（Langfuse 可见）
  5. 持久化到 EventStore（DB）
  6. 通过 SSEBridge 推送到前端

使用方式:
    emitter = EventEmitter()
    await emitter.emit(
        event_type=BusinessEventType.SCREENING_COMPLETED,
        entity_type="candidate",
        entity_id="xxx",
        domain_fields={"match_score": 0.85, "decision": "advance"},
    )
"""

from __future__ import annotations

import logging
from typing import Any

from app.agentops.core.context import get_context
from app.agentops.core.schemas import ScoreEvent
from app.agentops.events.schemas import BusinessEvent, BusinessEventType
from app.agentops.runtime import get_agentops_provider

logger = logging.getLogger(__name__)


# 哪些 domain_fields 的 key 需要同步导出为 Langfuse Score
_SCORE_EXPORT_KEYS: set[str] = {
    "match_score",
    "overall_score",
    "quality_score",
    "confidence",
    "final_score",
    "average_score",
}


class EventEmitter:
    """业务事件发射器 — 线程安全，无状态。"""

    async def emit(
        self,
        event_type: BusinessEventType,
        entity_type: str = "",
        entity_id: str = "",
        domain_fields: dict[str, Any] | None = None,
        *,
        user_id: str = "",
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        duration_ms: float | None = None,
        error: str = "",
    ) -> BusinessEvent | None:
        """发射一个业务事件。

        自动从当前 AgentOpsContext 继承 trace_id / span_id / parent_span_id，
        因此即使没有显式传 user_id/session_id，也能关联到执行链路。

        返回构造的 BusinessEvent（可用于后续关联），
        或在静默失败时返回 None（不打断业务逻辑）。
        """
        ctx = get_context()

        event = BusinessEvent(
            event_type=event_type,
            name=event_type.value,
            entity_type=entity_type,
            entity_id=entity_id,
            domain_fields=domain_fields or {},
            metadata=metadata or {},
            tags=tags or [],
            error=error,
            # 从 AgentOpsContext 继承
            trace_id=ctx.trace_id if ctx else "",
            span_id=ctx.span_id if ctx else "",
            parent_span_id=ctx.parent_span_id if ctx else "",
            user_id=user_id or (ctx.user_id if ctx else ""),
            session_id=session_id or (ctx.session_id if ctx else ""),
            tenant_id=ctx.tenant_id if ctx else "",
            request_id=ctx.request_id if ctx else "",
            operation_id=ctx.operation_id if ctx else "",
            environment=ctx.environment if ctx else "",
        )

        try:
            provider = get_agentops_provider()
            await provider.record_event(event)
        except Exception as exc:
            logger.warning("EventEmitter: failed to record event %s: %s", event_type, exc)
            # 不返回 None — 继续做 SSE 和 DB 持久化
        else:
            await self._export_scores(event, provider)

        await self._persist(event, duration_ms=duration_ms)

        # Publish to SSE bus for real-time frontend delivery
        await self._publish_sse(event)

        return event

    async def _export_scores(self, event: BusinessEvent, provider: Any) -> None:
        trace_id = event.trace_id
        if not trace_id:
            return
        for key, val in event.domain_fields.items():
            if key in _SCORE_EXPORT_KEYS and isinstance(val, (int, float)):
                try:
                    score_name = f"{event.event_type}.{key}"
                    await provider.record_score(ScoreEvent(
                        name=score_name,
                        trace_id=trace_id,
                        value=val,
                        comment=f"{event.entity_type}={event.entity_id}",
                        tags=list(event.tags) if event.tags else [],
                    ))
                except Exception as exc:
                    logger.debug("EventEmitter: score export skipped for %s: %s", key, exc)

    async def _persist(self, event: BusinessEvent, duration_ms: float | None = None) -> None:
        try:
            from app.agentops.events.store import write_event
            await write_event(event)
        except Exception as exc:
            logger.warning("EventEmitter: DB persist failed (non-blocking): %s", exc)

    async def _publish_sse(self, event: BusinessEvent) -> None:
        """通过 OperationEventBus 推送业务事件到 SSE 前端。"""
        try:
            from app.services.operation_service import event_bus

            event_bus.publish("business_event", {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "domain_fields": event.domain_fields,
                "trace_id": event.trace_id,
                "user_id": event.user_id,
                "session_id": event.session_id,
                "timestamp": event.timestamp,
                "tags": event.tags,
                "error": event.error,
            })
        except Exception as exc:
            logger.warning("EventEmitter: SSE publish failed (non-blocking): %s", exc)


# 模块级单例（轻量无状态，允许多实例）
_emitter: EventEmitter | None = None


def get_event_emitter() -> EventEmitter:
    global _emitter
    if _emitter is None:
        _emitter = EventEmitter()
    return _emitter
