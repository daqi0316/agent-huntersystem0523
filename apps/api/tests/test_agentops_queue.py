import pytest

from app.agentops.core.schemas import BaseEvent, TraceEvent
from app.agentops.reliability import AgentOpsQueue, CircuitBreaker

pytestmark = pytest.mark.asyncio


async def test_queue_exports_events_and_updates_stats():
    exported = []

    async def exporter(event: BaseEvent) -> None:
        exported.append(event.name)

    queue = AgentOpsQueue(exporter=exporter, max_size=2)
    assert queue.enqueue(TraceEvent(name="one")) is True
    assert queue.enqueue(TraceEvent(name="two")) is True

    await queue.flush()

    assert exported == ["one", "two"]
    assert queue.stats.accepted == 2
    assert queue.stats.exported == 2
    assert queue.size() == 0


async def test_queue_drops_new_event_when_full():
    async def exporter(event: BaseEvent) -> None:
        _ = event
        return None

    queue = AgentOpsQueue(exporter=exporter, max_size=1)

    assert queue.enqueue(TraceEvent(name="one")) is True
    assert queue.enqueue(TraceEvent(name="two")) is False
    assert queue.stats.dropped == 1


async def test_queue_isolates_exporter_failures_and_opens_circuit():
    async def exporter(event: BaseEvent) -> None:
        _ = event
        raise RuntimeError("down")

    queue = AgentOpsQueue(
        exporter=exporter,
        max_size=3,
        circuit_breaker=CircuitBreaker(failure_threshold=1, recovery_seconds=60),
    )
    queue.enqueue(TraceEvent(name="one"))
    queue.enqueue(TraceEvent(name="two"))

    await queue.flush()

    assert queue.stats.failed == 1
    assert queue.stats.circuit_open_drops == 1
