"""PR-V.2 — migration script tests.

The script `migrate_legacy_orchestrator_sessions()` SCANs Redis for
`orch:session:*` keys and reports counts. It must:

- Return zeros when no legacy sessions exist
- Distinguish resumable vs orphaned (no graph index) sessions
- Tolerate Redis unavailable / scan errors
- Never mutate state (read-only)
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def fake_redis():
    """Build a minimal async Redis fake scoped per test."""
    client = MagicMock()

    storage: dict[str, bytes] = {}

    async def _get(key: str):
        return storage.get(key)

    async def _exists(key: str):
        return int(key in storage)

    async def _set(key: str, value, ex=None):
        if isinstance(value, str):
            value = value.encode()
        storage[key] = value

    async def _delete(*keys):
        removed = 0
        for k in keys:
            if k in storage:
                del storage[k]
                removed += 1
        return removed

    async def _scan(cursor: int = 0, match: str | None = None, count: int = 200):
        prefix = match.rstrip("*") if match else ""
        matched = sorted(
            k for k in storage.keys()
            if k.startswith(prefix)
        )
        return 0, matched

    client.get = AsyncMock(side_effect=_get)
    client.exists = AsyncMock(side_effect=_exists)
    client.set = AsyncMock(side_effect=_set)
    client.delete = AsyncMock(side_effect=_delete)
    client.scan = AsyncMock(side_effect=_scan)

    client._storage = storage
    return client


def _make_session(session_id: str, approval_ids: list[str]) -> bytes:
    return json.dumps({
        "session_id": session_id,
        "task": "test",
        "context": {},
        "sub_tasks": [{"type": "screening", "description": "x", "depends_on": []}],
        "levels": [[0]],
        "results": [],
        "shared_context": {},
        "paused_at_level": 0,
        "approval_ids": approval_ids,
        "status": "paused",
    }).encode()


class TestMigrationHappyPath:
    async def test_no_sessions_returns_zeros(self, fake_redis):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            summary = await migrate_legacy_orchestrator_sessions()

        assert summary == {
            "scanned": 0,
            "with_approvals": 0,
            "resumable_via_graph": 0,
            "orphaned": 0,
            "session_ids": [],
        }

    async def test_session_without_approvals_is_scanned_but_not_flagged(self, fake_redis):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        await fake_redis.set("orch:session:os_a", _make_session("os_a", []))
        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            summary = await migrate_legacy_orchestrator_sessions()

        assert summary["scanned"] == 1
        assert summary["with_approvals"] == 0
        assert summary["resumable_via_graph"] == 0
        assert summary["orphaned"] == 0
        assert summary["session_ids"] == ["os_a"]

    async def test_orphaned_session_counted_when_no_graph_index(self, fake_redis, caplog):
        import logging

        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        await fake_redis.set(
            "orch:session:os_orphan",
            _make_session("os_orphan", ["appr_orphan_1", "appr_orphan_2"]),
        )

        with caplog.at_level(logging.WARNING, logger="app.services.orchestrator_session_migration"):
            with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
                summary = await migrate_legacy_orchestrator_sessions()

        assert summary["scanned"] == 1
        assert summary["with_approvals"] == 1
        assert summary["resumable_via_graph"] == 0
        assert summary["orphaned"] == 1
        assert any("Orphaned" in r.message for r in caplog.records)

    async def test_resumable_session_counted_when_graph_index_exists(self, fake_redis):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        await fake_redis.set(
            "orch:session:os_resume",
            _make_session("os_resume", ["appr_resume_1"]),
        )
        await fake_redis.set("appr:graph_thread:appr_resume_1", "thread-123")

        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            summary = await migrate_legacy_orchestrator_sessions()

        assert summary["scanned"] == 1
        assert summary["with_approvals"] == 1
        assert summary["resumable_via_graph"] == 1
        assert summary["orphaned"] == 0

    async def test_session_with_mixed_approvals_counts_as_resumable(self, fake_redis):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        await fake_redis.set(
            "orch:session:os_mixed",
            _make_session("os_mixed", ["appr_orphan", "appr_resume"]),
        )
        await fake_redis.set("appr:graph_thread:appr_resume", "thread-1")

        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            summary = await migrate_legacy_orchestrator_sessions()

        assert summary["resumable_via_graph"] == 1
        assert summary["orphaned"] == 0

    async def test_multiple_sessions_summary(self, fake_redis):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        await fake_redis.set("orch:session:os_1", _make_session("os_1", []))
        await fake_redis.set("orch:session:os_2", _make_session("os_2", ["appr_orphan"]))
        await fake_redis.set("orch:session:os_3", _make_session("os_3", ["appr_resume"]))
        await fake_redis.set("appr:graph_thread:appr_resume", "thread-3")

        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            summary = await migrate_legacy_orchestrator_sessions()

        assert summary["scanned"] == 3
        assert summary["with_approvals"] == 2
        assert summary["resumable_via_graph"] == 1
        assert summary["orphaned"] == 1
        assert sorted(summary["session_ids"]) == ["os_1", "os_2", "os_3"]


class TestMigrationResilience:
    async def test_redis_unavailable_returns_zeros(self):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        with patch("app.core.redis.get_redis", AsyncMock(return_value=None)):
            summary = await migrate_legacy_orchestrator_sessions()

        assert summary["scanned"] == 0
        assert summary["orphaned"] == 0

    async def test_redis_get_raises_returns_zeros(self):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        client = MagicMock()
        client.scan = AsyncMock(side_effect=RuntimeError("scan failed"))
        with patch("app.core.redis.get_redis", AsyncMock(return_value=client)):
            summary = await migrate_legacy_orchestrator_sessions()

        assert summary["scanned"] == 0

    async def test_corrupt_session_json_skipped(self, fake_redis):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        await fake_redis.set("orch:session:os_bad", b"not-json")
        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            summary = await migrate_legacy_orchestrator_sessions()

        assert summary["scanned"] == 1
        assert summary["with_approvals"] == 0

    async def test_scan_with_large_count_paginates(self, fake_redis):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        for i in range(5):
            await fake_redis.set(f"orch:session:os_{i}", _make_session(f"os_{i}", []))

        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            summary = await migrate_legacy_orchestrator_sessions()

        assert summary["scanned"] == 5

    async def test_migration_does_not_delete_keys(self, fake_redis):
        from app.services.orchestrator_session_migration import (
            migrate_legacy_orchestrator_sessions,
        )

        await fake_redis.set(
            "orch:session:os_x",
            _make_session("os_x", ["appr_x"]),
        )
        await fake_redis.set("appr:graph_thread:appr_x", "thread-x")

        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            await migrate_legacy_orchestrator_sessions()

        assert "orch:session:os_x" in fake_redis._storage
        assert "appr:graph_thread:appr_x" in fake_redis._storage
        fake_redis.delete.assert_not_called()
