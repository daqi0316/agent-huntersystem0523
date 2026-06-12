from __future__ import annotations

import logging
from collections.abc import Awaitable
from importlib import import_module
from typing import Protocol, cast

from app.core.config import settings

from .providers.base import AgentOpsProvider
from .providers.composite import CompositeProvider

logger = logging.getLogger(__name__)

_provider: AgentOpsProvider | None = None


class QueueRuntimeLike(Protocol):
    def flush_with_timeout(self, timeout_seconds: float) -> Awaitable[None]: ...


_queue: QueueRuntimeLike | None = None


def get_agentops_provider() -> AgentOpsProvider:
    global _provider
    if _provider is None:
        _provider = build_agentops_provider()
    return _provider


def build_agentops_provider() -> AgentOpsProvider:
    from app.agentops.cost.recorder import CostRecordingProvider

    # CostRecordingProvider 始终激活 — 即使 agentops 全局关闭
    cost_provider = CostRecordingProvider()

    if not settings.agentops_enabled:
        return CompositeProvider(providers=[cost_provider])
    if settings.agentops_provider.lower() != "langfuse":
        return CompositeProvider(providers=[cost_provider])

    exporters_module = import_module("app.agentops.exporters.langfuse_exporter")
    reliability_module = import_module("app.agentops.reliability.queue")
    composite_module = import_module("app.agentops.providers.composite")
    exporter_provider_module = import_module("app.agentops.providers.exporter_provider")
    langfuse_exporter_cls = exporters_module.LangfuseExporter
    queue_cls = reliability_module.AgentOpsQueue
    composite_provider_cls = composite_module.CompositeProvider
    exporter_provider_cls = exporter_provider_module.ExporterProvider

    exporter = langfuse_exporter_cls(
        enabled=True,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
    )
    queue = queue_cls(exporter=exporter.export, max_size=settings.agentops_queue_max_size)
    set_agentops_queue(queue)
    provider = composite_provider_cls(providers=[exporter_provider_cls(queue=queue), cost_provider])
    return cast(AgentOpsProvider, provider)


def set_agentops_provider(provider: AgentOpsProvider | None) -> None:
    global _provider
    _provider = provider


def set_agentops_queue(queue: QueueRuntimeLike | None) -> None:
    global _queue
    _queue = queue


async def shutdown_agentops() -> None:
    queue = _queue
    provider = _provider
    try:
        if queue is not None:
            await queue.flush_with_timeout(settings.agentops_flush_timeout_seconds)
    except Exception as exc:
        logger.warning("agentops queue shutdown failed: %s", exc)
    try:
        if provider is not None:
            await provider.shutdown()
    except Exception as exc:
        logger.warning("agentops provider shutdown failed: %s", exc)
