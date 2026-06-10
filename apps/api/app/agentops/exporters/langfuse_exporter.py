"""LangfuseExporter — 将 AgentOps 事件导出到 Langfuse。

支持的事件类型:
- EVAL_SCORE_CREATED → client.score()
- TRACE_STARTED / COMPLETED / FAILED → client.trace() / trace.update()
- SPAN_STARTED / COMPLETED / FAILED → parent.{span,end}()
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Protocol, cast

from app.agentops.core.schemas import BaseEvent, EventType, ScoreEvent, SpanEvent

logger = logging.getLogger(__name__)


# ── 协议：Langfuse 客户端的 trace/span 接口 ──


class LangfuseTraceLike(Protocol):
    def span(self, **kwargs: Any) -> Any: ...
    def update(self, **kwargs: Any) -> Any: ...
    def end(self, **kwargs: Any) -> Any: ...


class LangfuseSpanLike(Protocol):
    def span(self, **kwargs: Any) -> Any: ...
    def end(self, **kwargs: Any) -> Any: ...
    def update(self, **kwargs: Any) -> Any: ...


class LangfuseClientLike(Protocol):
    def score(self, **kwargs: Any) -> Any: ...
    def trace(self, **kwargs: Any) -> Any: ...
    def span(self, **kwargs: Any) -> Any: ...
    def flush(self) -> Any: ...
    def shutdown(self) -> Any: ...


# ── LangfuseExporter ──


@dataclass(slots=True)
class LangfuseExporter:
    enabled: bool = False
    client: LangfuseClientLike | None = None
    public_key: str = ""
    secret_key: str = ""
    base_url: str = ""

    # 活跃 trace / span 缓存 — 用于关联 start → end 事件
    _traces: dict[str, Any] = field(default_factory=dict, repr=False)
    _spans: dict[str, Any] = field(default_factory=dict, repr=False)

    async def export(self, event: BaseEvent) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            self._export_with_client(client, event)
        except Exception as exc:
            logger.debug("langfuse export skipped (%s) for %s: %s", type(event).__name__, event.name, exc)

    async def flush(self) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            _ = client.flush()
        except Exception as exc:
            logger.warning("langfuse flush failed: %s", exc)

    async def shutdown(self) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            _ = client.shutdown()
        except Exception as exc:
            logger.warning("langfuse shutdown failed: %s", exc)

    def _get_client(self) -> LangfuseClientLike | None:
        if not self.enabled:
            return None
        if self.client is not None:
            return self.client
        if not self.public_key or not self.secret_key:
            return None
        try:
            langfuse_module = import_module("langfuse")
            get_client = cast(Callable[[], LangfuseClientLike], langfuse_module.get_client)
        except Exception as exc:
            logger.warning("langfuse sdk unavailable: %s", exc)
            return None
        try:
            self.client = get_client()
        except Exception as exc:
            logger.warning("langfuse client init failed: %s", exc)
            return None
        return self.client

    # ── 事件分发 ──

    def _export_with_client(self, client: LangfuseClientLike, event: BaseEvent) -> None:
        raw_type = event.event_type

        # Score
        if raw_type == EventType.EVAL_SCORE_CREATED and isinstance(event, ScoreEvent):
            self._handle_score(client, event)
        # Trace lifecycle
        elif raw_type == EventType.TRACE_STARTED:
            self._handle_trace_start(client, event)
        elif raw_type == EventType.TRACE_COMPLETED:
            self._handle_trace_end(event, error=False)
        elif raw_type == EventType.TRACE_FAILED:
            self._handle_trace_end(event, error=True)
        # Span lifecycle
        elif raw_type == EventType.SPAN_STARTED:
            self._handle_span_start(client, event)
        elif raw_type == EventType.SPAN_COMPLETED:
            self._handle_span_end(event, error=False)
        elif raw_type == EventType.SPAN_FAILED:
            self._handle_span_end(event, error=True)

    # ── Score ──

    def _handle_score(self, client: LangfuseClientLike, event: ScoreEvent) -> None:
        client.score(
            trace_id=event.trace_id,
            name=event.score_name or event.name,
            value=event.value,
            comment=event.comment or None,
            metadata=event.metadata or None,
        )

    # ── Trace ──

    def _handle_trace_start(self, client: LangfuseClientLike, event: BaseEvent) -> None:
        trace = client.trace(
            id=event.trace_id,
            name=event.name,
            input=event.input,
            metadata=dict(event.metadata) if event.metadata else None,
            tags=list(event.tags) if event.tags else None,
            user_id=event.user_id or None,
            session_id=event.session_id or None,
        )
        self._traces[event.trace_id] = trace

    def _handle_trace_end(self, event: BaseEvent, *, error: bool) -> None:
        trace = self._traces.pop(event.trace_id, None)
        if trace is None:
            return
        kwargs: dict[str, Any] = {"output": event.output}
        if error and event.error:
            kwargs["metadata"] = {"error": event.error}
        trace.update(**kwargs)

    # ── Span ──

    def _handle_span_start(self, client: LangfuseClientLike, event: BaseEvent) -> None:
        # 查找父对象：优先按 parent_span_id 找 span，再按 trace_id 找 trace
        parent = self._spans.get(event.parent_span_id) or self._traces.get(event.trace_id)
        if parent is None:
            # 父不存在 → 用 client 建顶层 observation
            parent = client
        span = parent.span(
            id=event.span_id,
            name=event.name,
            input=event.input,
            metadata=dict(event.metadata) if event.metadata else None,
            tags=list(event.tags) if event.tags else None,
        )
        self._spans[event.span_id] = span

    def _handle_span_end(self, event: BaseEvent, *, error: bool) -> None:
        span = self._spans.pop(event.span_id, None)
        if span is None:
            return
        # 有 duration_ms 时转成秒传入
        duration = None
        if isinstance(event, SpanEvent) and event.duration_ms is not None:
            duration = event.duration_ms / 1000.0

        kwargs: dict[str, Any] = {"output": event.output}
        if duration is not None:
            kwargs["end_time"] = duration  # Langfuse SDK 支持相对 duration
        if error and event.error:
            if event.metadata:
                kwargs["metadata"] = {**dict(event.metadata), "error": event.error}
            else:
                kwargs["metadata"] = {"error": event.error}
        span.end(**kwargs)
