"""Tests for MessageBus — async event bus with pub/sub and history."""

import pytest

from app.agents.message_bus import Event, EventType, MessageBus, get_message_bus


# ── Event ──


def test_event_creation():
    e = Event(EventType.SCREENING_COMPLETED, {"candidate_id": "c-1"}, source="screening")
    assert e.type == EventType.SCREENING_COMPLETED
    assert e.payload == {"candidate_id": "c-1"}
    assert e.source == "screening"
    assert e.id is not None
    assert e.timestamp > 0


def test_event_defaults():
    e = Event(EventType.AGENT_ERROR, {"msg": "fail"})
    assert e.source == ""
    assert e.aggregate_id is None


def test_event_repr():
    e = Event(EventType.CANDIDATE_MOVED, {"stage": "hired"}, source="pipeline")
    r = repr(e)
    assert e.type.value in r
    assert e.source in r


# ── MessageBus ──


@pytest.mark.asyncio
async def test_publish_empty_subscribers():
    bus = MessageBus()
    e = await bus.publish(EventType.SCREENING_COMPLETED, {"ok": True})
    assert e.type == EventType.SCREENING_COMPLETED
    assert e.payload == {"ok": True}


@pytest.mark.asyncio
async def test_subscribe_and_publish():
    bus = MessageBus()
    received: list[Event] = []

    async def handler(event: Event):
        received.append(event)

    await bus.subscribe(EventType.SCREENING_COMPLETED, handler)
    e = await bus.publish(EventType.SCREENING_COMPLETED, {"candidate_id": "c-1"})
    assert len(received) == 1
    assert received[0].id == e.id


@pytest.mark.asyncio
async def test_multiple_subscribers():
    bus = MessageBus()
    results: list[str] = []

    async def h1(e: Event):
        results.append("h1")

    async def h2(e: Event):
        results.append("h2")

    await bus.subscribe(EventType.TASK_COMPLETED, h1)
    await bus.subscribe(EventType.TASK_COMPLETED, h2)
    await bus.publish(EventType.TASK_COMPLETED, {})
    assert sorted(results) == ["h1", "h2"]


@pytest.mark.asyncio
async def test_handler_exception_does_not_crash_bus():
    bus = MessageBus()

    async def failing(_e: Event):
        raise ValueError("boom")

    async def ok(_e: Event):
        pass

    await bus.subscribe(EventType.INTERVIEW_SCHEDULED, failing)
    await bus.subscribe(EventType.INTERVIEW_SCHEDULED, ok)
    e = await bus.publish(EventType.INTERVIEW_SCHEDULED, {})
    assert e is not None  # bus survived


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = MessageBus()

    async def handler(_e: Event):
        pass

    await bus.subscribe(EventType.OFFER_SENT, handler)
    assert await bus.unsubscribe(EventType.OFFER_SENT, handler) is True
    assert await bus.unsubscribe(EventType.OFFER_SENT, handler) is False


@pytest.mark.asyncio
async def test_history():
    bus = MessageBus()
    await bus.publish(EventType.SCREENING_COMPLETED, {"id": "1"}, source="s1")
    await bus.publish(EventType.INTERVIEW_SCHEDULED, {"id": "2"}, source="s2")
    await bus.publish(EventType.SCREENING_COMPLETED, {"id": "3"}, source="s1")
    assert len(bus.history()) == 3
    assert len(bus.history(type=EventType.SCREENING_COMPLETED)) == 2
    assert len(bus.history(source="s1")) == 2


@pytest.mark.asyncio
async def test_history_filter_aggregate_id():
    bus = MessageBus()
    await bus.publish(EventType.CANDIDATE_MOVED, {}, aggregate_id="c-1")
    await bus.publish(EventType.CANDIDATE_MOVED, {}, aggregate_id="c-2")
    await bus.publish(EventType.CANDIDATE_MOVED, {}, aggregate_id="c-1")
    assert len(bus.history(aggregate_id="c-1")) == 2


@pytest.mark.asyncio
async def test_history_limit():
    bus = MessageBus(max_history=100)
    for i in range(20):
        await bus.publish(EventType.SYSTEM_NOTIFICATION, {"i": i})
    assert len(bus.history(limit=5)) == 5
    assert len(bus.history()) == 20


@pytest.mark.asyncio
async def test_history_max_capacity():
    bus = MessageBus(max_history=5)
    for i in range(10):
        await bus.publish(EventType.SYSTEM_NOTIFICATION, {"i": i})
    assert len(bus.history()) == 5


@pytest.mark.asyncio
async def test_clear_history():
    bus = MessageBus()
    await bus.publish(EventType.AGENT_LOG, {"msg": "test"})
    assert len(bus.history()) == 1
    await bus.clear_history()
    assert len(bus.history()) == 0


@pytest.mark.asyncio
async def test_subscriber_count():
    bus = MessageBus()

    async def h1(_e):
        pass

    async def h2(_e):
        pass

    assert bus.subscriber_count == 0
    await bus.subscribe(EventType.TASK_DELEGATED, h1)
    await bus.subscribe(EventType.TASK_DELEGATED, h2)
    await bus.subscribe(EventType.TASK_COMPLETED, h1)
    assert bus.subscriber_count == 3


@pytest.mark.asyncio
async def test_get_message_bus_singleton():
    b1 = get_message_bus()
    b2 = get_message_bus()
    assert b1 is b2
