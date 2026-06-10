"""trace_llm_generation — LLM 调用级 trace context manager。

与 agent_span 不同，本工具专为 LLM chat completion 调用设计，
自动记录 LLM_GENERATION_STARTED / COMPLETED / FAILED 事件。

用法:
    from app.agentops.tracing.llm_generation import trace_llm_generation

    async with trace_llm_generation(model=llm.model, provider=llm.provider,
                                    input={"messages": [...]}) as span:
        resp = await llm.client.chat.completions.create(...)
        span.set_usage(resp.usage)           # 可选
        span.set_output({"content": ...})    # 可选
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from app.agentops.core.context import AgentOpsContext, get_context
from app.agentops.core.schemas import EventType, LLMGenerationEvent
from app.agentops.runtime import get_agentops_provider

logger = logging.getLogger(__name__)


@asynccontextmanager
async def trace_llm_generation(
    *,
    model: str,
    provider: str = "",
    input: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
    span_name: str = "llm.chat",
) -> AsyncIterator[LLMGenerationSpan]:
    """包裹一次 LLM chat completion 调用，自动记录 LLM 生成事件。

    参数:
        model: 模型名称
        provider: 提供商名称
        input: 输入数据（messages 等，将 sanitize 后写入事件）
        parameters: 调用参数（temperature, max_tokens 等）
        span_name: 事件名称（默认 "llm.chat"）

    用法:
        async with trace_llm_generation(model=llm.model, input={"messages": msgs}) as span:
            resp = await llm.client.chat.completions.create(...)
            span.set_usage(resp.usage)
            span.set_output({"content": resp.choices[0].message.content})
    """
    provider_instance = get_agentops_provider()
    ctx = get_context() or AgentOpsContext()

    generation_id = str(uuid4())
    start_time = time.monotonic()

    # 构造起始事件
    base = LLMGenerationEvent(
        name=span_name,
        event_type=EventType.LLM_GENERATION_STARTED,
        trace_id=ctx.trace_id,
        span_id=generation_id,
        parent_span_id=ctx.span_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        model=model,
        provider=provider,
        parameters=parameters or {},
        input=input,
    )

    try:
        await provider_instance.record_generation(base)
    except Exception as exc:
        logger.debug("trace_llm_generation start failed (non-blocking): %s", exc)

    span = LLMGenerationSpan(
        provider=provider_instance,
        name=span_name,
        generation_id=generation_id,
        trace_id=ctx.trace_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        model=model,
        provider_name=provider,
        start_time=start_time,
    )

    try:
        yield span
    except BaseException as exc:
        await span._fail(exc)
        raise
    else:
        await span._complete()


class LLMGenerationSpan:
    """LLM 生成 span 句柄，允许设置 usage 和 output。"""

    def __init__(
        self,
        *,
        provider: Any,
        name: str,
        generation_id: str,
        trace_id: str,
        user_id: str,
        session_id: str,
        model: str,
        provider_name: str,
        start_time: float,
    ) -> None:
        self._provider = provider
        self._name = name
        self._generation_id = generation_id
        self._trace_id = trace_id
        self._user_id = user_id
        self._session_id = session_id
        self._model = model
        self._provider_name = provider_name
        self._start_time = start_time
        self._usage: Any = None
        self._output: dict[str, Any] | None = None

    def set_usage(self, usage: Any) -> None:
        """设置 token usage（通常来自 resp.usage）。"""
        self._usage = usage

    def set_output(self, output: dict[str, Any] | None) -> None:
        """设置输出数据。"""
        self._output = output

    # ── 内部 ──

    async def _complete(self) -> None:
        duration_ms = (time.monotonic() - self._start_time) * 1000
        usage = self._usage
        event = LLMGenerationEvent(
            name=self._name,
            event_type=EventType.LLM_GENERATION_COMPLETED,
            trace_id=self._trace_id,
            user_id=self._user_id,
            session_id=self._session_id,
            model=self._model,
            provider=self._provider_name,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            duration_ms=duration_ms,
            output=self._output,
        )
        try:
            await self._provider.record_generation(event)
        except Exception as exc:
            logger.debug("trace_llm_generation complete failed (non-blocking): %s", exc)

    async def _fail(self, exc: BaseException) -> None:
        duration_ms = (time.monotonic() - self._start_time) * 1000
        event = LLMGenerationEvent(
            name=self._name,
            event_type=EventType.LLM_GENERATION_FAILED,
            trace_id=self._trace_id,
            user_id=self._user_id,
            session_id=self._session_id,
            duration_ms=duration_ms,
            error=str(exc)[:2000],
            output=self._output,
        )
        try:
            await self._provider.record_generation(event)
        except Exception as exc2:
            logger.debug("trace_llm_generation fail event failed (non-blocking): %s", exc2)
