"""Tests for AuditLogger — agent operation audit log with ring buffer."""

import pytest

from app.agents.audit_logger import AuditEntry, AuditLogger, get_audit_logger


# ── AuditEntry ──


def test_audit_entry_defaults():
    e = AuditEntry()
    assert e.id is not None
    assert e.timestamp > 0
    assert e.user_id == ""
    assert e.success is True
    assert e.tags == []


def test_audit_entry_to_dict():
    e = AuditEntry(user_id="u-1", agent_name="screening", action="screen")
    d = e.to_dict()
    assert d["user_id"] == "u-1"
    assert d["agent_name"] == "screening"
    assert d["action"] == "screen"


def test_audit_entry_datetime_iso():
    e = AuditEntry()
    iso = e.datetime_iso
    assert "T" in iso
    assert iso.endswith("+00:00")


# ── AuditLogger ──


@pytest.mark.asyncio
async def test_record_and_query():
    logger = AuditLogger(max_entries=100)
    await logger.record(
        user_id="u-1",
        agent_name="screening",
        action="screen_resume",
        input_summary="candidate=c-1",
        output_summary="score=85",
        duration_ms=1200,
        success=True,
        tags=["fast", "high-score"],
    )
    results = logger.query(agent_name="screening")
    assert len(results) == 1
    assert results[0]["action"] == "screen_resume"
    assert results[0]["duration_ms"] == 1200


@pytest.mark.asyncio
async def test_query_by_user():
    logger = AuditLogger()
    await logger.record(user_id="u-1", agent_name="a1", action="act1")
    await logger.record(user_id="u-2", agent_name="a2", action="act2")
    assert len(logger.query(user_id="u-1")) == 1
    assert len(logger.query(user_id="u-3")) == 0


@pytest.mark.asyncio
async def test_query_by_success():
    logger = AuditLogger()
    await logger.record(action="ok", success=True)
    await logger.record(action="fail", success=False)
    assert len(logger.query(success=True)) == 1
    assert len(logger.query(success=False)) == 1


@pytest.mark.asyncio
async def test_query_by_tag():
    logger = AuditLogger()
    await logger.record(action="a1", tags=["urgent"])
    await logger.record(action="a2", tags=["normal"])
    assert len(logger.query(tag="urgent")) == 1


@pytest.mark.asyncio
async def test_query_limit_and_offset():
    logger = AuditLogger()
    for i in range(10):
        await logger.record(action=f"act-{i}")
    assert len(logger.query(limit=3)) == 3
    # offset should skip from the end (most recent first conceptually)
    q = logger.query(limit=5)
    assert len(q) == 5


@pytest.mark.asyncio
async def test_max_entries_ring_buffer():
    logger = AuditLogger(max_entries=3)
    for i in range(5):
        await logger.record(action=f"act-{i}")
    assert len(logger.query()) == 3
    # most recent 3 should remain
    actions = [e["action"] for e in logger.query()]
    assert "act-2" in actions
    assert "act-4" in actions
    assert "act-0" not in actions


@pytest.mark.asyncio
async def test_stats():
    logger = AuditLogger()
    await logger.record(action="a1", agent_name="ag1", success=True)
    await logger.record(action="a1", agent_name="ag1", success=True)
    await logger.record(action="a2", agent_name="ag2", success=False)
    s = logger.stats()
    assert s["total_entries"] == 3
    assert s["success_rate"] == pytest.approx(66.7, rel=1)
    assert s["by_agent"]["ag1"] == 2
    assert s["by_action"]["a2"] == 1


@pytest.mark.asyncio
async def test_stats_empty():
    logger = AuditLogger()
    s = logger.stats()
    assert s["total_entries"] == 0
    assert s["success_rate"] == 0


@pytest.mark.asyncio
async def test_persist_hook():
    logger = AuditLogger(max_entries=10)
    hooked: list[AuditEntry] = []

    async def hook(entry: AuditEntry):
        hooked.append(entry)

    logger.add_persist_hook(hook)
    await logger.record(action="test", success=True)
    assert len(hooked) == 1
    assert hooked[0].action == "test"


@pytest.mark.asyncio
async def test_persist_hook_failure_does_not_crash():
    logger = AuditLogger()
    async def failing(_e):
        raise RuntimeError("hook failed")
    logger.add_persist_hook(failing)
    entry = await logger.record(action="should-not-crash")
    assert entry.action == "should-not-crash"


@pytest.mark.asyncio
async def test_clear():
    logger = AuditLogger()
    await logger.record(action="x")
    assert len(logger.query()) == 1
    await logger.clear()
    assert len(logger.query()) == 0


@pytest.mark.asyncio
async def test_get_audit_logger_singleton():
    l1 = get_audit_logger()
    l2 = get_audit_logger()
    assert l1 is l2
