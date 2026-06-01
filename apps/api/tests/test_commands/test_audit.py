"""Tests for CommandAuditService — 验证 fire-and-forget 写入与查询."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.commands.audit import CommandAuditService, fire_and_forget


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


class TestCommandAuditServiceRecord:
    @pytest.mark.asyncio
    async def test_no_db_returns_none(self) -> None:
        svc = CommandAuditService(db=None)
        result = await svc.record(command_name="/help")
        assert result is None

    @pytest.mark.asyncio
    async def test_record_success_persists_entry(self, mock_db: AsyncMock) -> None:
        svc = CommandAuditService(db=mock_db)
        entry = await svc.record(
            command_name="/help",
            args=[],
            flags={},
            result_code="success",
            duration_ms=12.3,
            session_id="sess-1",
            user_id="user-1",
        )
        assert entry is not None
        assert entry.command_name == "/help"
        assert entry.result_code == "success"
        assert entry.duration_ms == 12.3
        assert entry.session_id == "sess-1"
        assert entry.user_id == "user-1"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_passes_all_9_required_fields(self, mock_db: AsyncMock) -> None:
        """plan V.1 退出标准: 9 个字段必须都写库."""
        svc = CommandAuditService(db=mock_db)
        await svc.record(
            command_name="/delete",
            args=["candidate_123"],
            flags={"--force": True},
            result_code="denied",
            duration_ms=5.0,
            session_id="sess-X",
            user_id="user-X",
            confirmation_token="tok-abc",
            error_message="L2 required",
        )
        # 抓取 add() 调用的入参
        call_args = mock_db.add.call_args
        entry = call_args[0][0]
        assert entry.command_name == "/delete"
        assert entry.args == ["candidate_123"]
        assert entry.flags == {"--force": True}
        assert entry.result_code == "denied"
        assert entry.duration_ms == 5.0
        assert entry.session_id == "sess-X"
        assert entry.user_id == "user-X"
        assert entry.confirmation_token == "tok-abc"
        assert entry.error_message == "L2 required"
        # 9 个必填字段: id + command_name + args + flags + result_code
        #            + duration_ms + confirmation_token + session_id + user_id + error_message
        assert entry.id is not None

    @pytest.mark.asyncio
    async def test_record_failure_swallows_exception(self, mock_db: AsyncMock) -> None:
        mock_db.commit.side_effect = RuntimeError("DB down")
        svc = CommandAuditService(db=mock_db)
        result = await svc.record(command_name="/help")
        assert result is None
        mock_db.rollback.assert_awaited_once()  # 失败时回滚

    @pytest.mark.asyncio
    async def test_record_rollback_failure_also_swallowed(self, mock_db: AsyncMock) -> None:
        mock_db.commit.side_effect = RuntimeError("DB down")
        mock_db.rollback.side_effect = RuntimeError("rollback failed")
        svc = CommandAuditService(db=mock_db)
        # 不应抛异常
        result = await svc.record(command_name="/help")
        assert result is None


class TestCommandAuditServiceListRecent:
    @pytest.mark.asyncio
    async def test_list_recent_no_db_returns_empty(self) -> None:
        svc = CommandAuditService(db=None)
        rows = await svc.list_recent()
        assert rows == []

    @pytest.mark.asyncio
    async def test_list_recent_applies_filters(self, mock_db: AsyncMock) -> None:
        fake_rows = [MagicMock(), MagicMock()]
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = fake_rows
        mock_db.execute.return_value = execute_result

        svc = CommandAuditService(db=mock_db)
        rows = await svc.list_recent(
            command_name="/help",
            session_id="sess-1",
            user_id="user-1",
            limit=10,
        )
        assert rows == fake_rows
        # 确认 SQLAlchemy 查询被调用(具体 SQL 留给 SQLAlchemy 测试)
        mock_db.execute.assert_awaited_once()


class TestFireAndForget:
    @pytest.mark.asyncio
    async def test_fire_and_forget_creates_task(self) -> None:
        mock_db = AsyncMock()
        svc = CommandAuditService(db=mock_db)
        # 在已有 loop 的情况下,fire_and_forget 应该 create_task
        fire_and_forget(
            svc,
            command_name="/help",
            result_code="success",
            session_id="sess-FF",
        )
        # 至少会调用 db.add
        # (任务尚未调度,需要 yield)
        import asyncio
        await asyncio.sleep(0)
        mock_db.add.assert_called_once()
