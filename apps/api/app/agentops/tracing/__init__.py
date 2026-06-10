"""agent_span — Agent 级 span 辅助工具。

用法:
    from app.agentops.tracing import agent_span

    async with agent_span("intent_recognition", input={"text": text}):
        result = await do_something()
"""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from app.agentops.core.context import AgentOpsContext, get_context
from app.agentops.core.schemas import EventType, SpanEvent
from app.agentops.runtime import get_agentops_provider

logger = logging.getLogger(__name__)


@asynccontextmanager
async def agent_span(
    name: str,
    *,
    span_id: str | None = None,
    input: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> AsyncIterator[AgentOpsSpan]:
    """包裹一个异步操作，自动记录 span start/completed/failed 到 AgentOps provider。

    参数:
        name: span 名称（如 "intent_recognition", "agent.screening"）
        span_id: 可选，显式指定 span_id（默认自动生成）
        input: 输入数据（将经过 sanitize 后写入 span）
        tags: 附加标签

    用法:
        async with agent_span("intent_recognition", input={"text": text}) as span:
            span.set_output({"intent": "screening"})
            result = await do_something()

    异常时自动记录 SPAN_FAILED，然后重新抛出。
    """
    provider = get_agentops_provider()
    ctx = get_context() or AgentOpsContext()

    sid = span_id or str(uuid4())
    parent_span_id = ctx.span_id

    # 构造 child context（新 span_id，parent=当前 span_id）
    child_ctx = AgentOpsContext(
        trace_id=ctx.trace_id,
        span_id=sid,
        parent_span_id=parent_span_id,
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        session_id=ctx.session_id,
        request_id=ctx.request_id,
        operation_id=ctx.operation_id,
        environment=ctx.environment,
        service=ctx.service,
    )

    span = AgentOpsSpan(provider=provider, context=child_ctx, name=name)

    try:
        with span._activate_context():
            await span._start(input=input, tags=tags)
            yield span
    except BaseException as exc:
        await span._fail(exc)
        raise
    else:
        await span._complete()


class AgentOpsSpan:
    """Span 句柄，允许在包裹块内设置 output/metadata。"""

    def __init__(
        self,
        provider: Any,
        context: AgentOpsContext,
        name: str,
    ) -> None:
        self._provider = provider
        self._context = context
        self._name = name
        self._start_time: float = 0.0
        self._output: dict[str, Any] | None = None
        self._metadata: dict[str, Any] | None = None

    # -- 公开 API --

    @property
    def span_id(self) -> str:
        return self._context.span_id

    @property
    def trace_id(self) -> str:
        return self._context.trace_id

    def set_output(self, output: dict[str, Any] | None) -> None:
        self._output = output

    def set_metadata(self, metadata: dict[str, Any] | None) -> None:
        self._metadata = metadata

    # -- 内部 --

    def _activate_context(self):
        """临时将 contextvar 切到 child 上下文（span 执行期间）。"""
        from app.agentops.core.context import reset_context, set_context

        token = set_context(self._context)
        from contextlib import contextmanager as _ctxmgr

        @_ctxmgr
        def _mgr():
            try:
                yield
            finally:
                reset_context(token)

        return _mgr()

    async def _start(
        self, *, input: dict[str, Any] | None = None, tags: list[str] | None = None
    ) -> None:
        self._start_time = time.monotonic()
        event = SpanEvent(
            name=self._name,
            event_type=EventType.SPAN_STARTED,
            trace_id=self._context.trace_id,
            span_id=self._context.span_id,
            parent_span_id=self._context.parent_span_id,
            user_id=self._context.user_id,
            session_id=self._context.session_id,
            input=input,
            tags=tags or [],
        )
        try:
            await self._provider.start_span(event)
        except Exception as exc:
            logger.debug("agent_span start failed (non-blocking): %s", exc)

    async def _complete(self) -> None:
        duration_ms = (time.monotonic() - self._start_time) * 1000
        event = SpanEvent(
            name=self._name,
            event_type=EventType.SPAN_COMPLETED,
            trace_id=self._context.trace_id,
            span_id=self._context.span_id,
            parent_span_id=self._context.parent_span_id,
            user_id=self._context.user_id,
            session_id=self._context.session_id,
            duration_ms=duration_ms,
            output=self._output,
            metadata=self._metadata or {},
        )
        try:
            await self._provider.record_event(event)
        except Exception as exc:
            logger.debug("agent_span complete failed (non-blocking): %s", exc)

    async def _fail(self, exc: BaseException) -> None:
        duration_ms = (time.monotonic() - self._start_time) * 1000
        event = SpanEvent(
            name=self._name,
            event_type=EventType.SPAN_FAILED,
            trace_id=self._context.trace_id,
            span_id=self._context.span_id,
            parent_span_id=self._context.parent_span_id,
            user_id=self._context.user_id,
            session_id=self._context.session_id,
            duration_ms=duration_ms,
            error=str(exc)[:2000],
            metadata=self._metadata or {},
        )
        try:
            await self._provider.record_event(event)
        except Exception as exc2:
            logger.debug("agent_span fail event failed (non-blocking): %s", exc2)
