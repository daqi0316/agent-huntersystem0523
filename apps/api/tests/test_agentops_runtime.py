import pytest

from app.agentops.core.schemas import ScoreEvent
from app.agentops.providers.composite import CompositeProvider
from app.agentops.providers.noop import NoopProvider
from app.agentops.runtime import (
    build_agentops_provider,
    set_agentops_provider,
    set_agentops_queue,
    shutdown_agentops,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_runtime():
    set_agentops_provider(None)
    set_agentops_queue(None)
    yield
    set_agentops_provider(None)
    set_agentops_queue(None)


async def test_build_agentops_provider_returns_noop_when_disabled(monkeypatch):
    monkeypatch.setattr("app.agentops.runtime.settings.agentops_enabled", False)

    provider = build_agentops_provider()

    assert isinstance(provider, NoopProvider)


async def test_build_agentops_provider_returns_noop_for_unknown_provider(monkeypatch):
    monkeypatch.setattr("app.agentops.runtime.settings.agentops_enabled", True)
    monkeypatch.setattr("app.agentops.runtime.settings.agentops_provider", "unknown")

    provider = build_agentops_provider()

    assert isinstance(provider, NoopProvider)


async def test_build_agentops_provider_uses_queue_when_langfuse_enabled(monkeypatch):
    monkeypatch.setattr("app.agentops.runtime.settings.agentops_enabled", True)
    monkeypatch.setattr("app.agentops.runtime.settings.agentops_provider", "langfuse")
    monkeypatch.setattr("app.agentops.runtime.settings.langfuse_public_key", "pk-test")
    monkeypatch.setattr("app.agentops.runtime.settings.langfuse_secret_key", "sk-test")

    provider = build_agentops_provider()

    assert isinstance(provider, CompositeProvider)
    await provider.record_score(ScoreEvent(name="score", score_name="quality", value=1))


async def test_shutdown_agentops_is_failure_isolated(monkeypatch):
    class FailingQueue:
        async def flush_with_timeout(self, timeout_seconds: float) -> None:
            _ = timeout_seconds
            raise RuntimeError("queue down")

    class FailingProvider:
        async def shutdown(self) -> None:
            raise RuntimeError("provider down")

    monkeypatch.setattr("app.agentops.runtime.settings.agentops_flush_timeout_seconds", 0.01)
    set_agentops_queue(FailingQueue())
    set_agentops_provider(FailingProvider())

    await shutdown_agentops()
