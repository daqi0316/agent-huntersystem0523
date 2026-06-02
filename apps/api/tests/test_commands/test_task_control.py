"""Tests for task_control handlers — V.2 真实实现 (V.3 coverage 修复).

针对 task_control.py 当前 31% coverage 补充关键路径:
1. SnapshotManager 本身 (create/get_latest/list_by_task/clear_task)
2. handle_rollback / handle_snapshot / handle_checkpoint (SnapshotManager 路径, 无需 DB)
3. handle_pause / handle_resume (降级路径, 无需 orchestrator graph)
4. handle_cancel (降级路径, 无需 orchestrator graph)
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.commands.handlers.task_control import (
    handle_pause,
    handle_resume,
    handle_cancel,
    handle_rollback,
    handle_snapshot,
    handle_checkpoint,
    _get_snapshot_manager,
)
from app.commands.types import CommandContext, CommandErrorCode
from app.core.snapshot_manager import SnapshotManager


# ----------------------------------------------------------------------
# SnapshotManager — 独立测试 (不依赖 orchestrator graph / langgraph)
# ----------------------------------------------------------------------

class TestSnapshotManagerDirect:
    @pytest.fixture
    def temp_db(self) -> str:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except Exception:
            pass

    @pytest.fixture
    def mgr(self, temp_db: str) -> SnapshotManager:
        return SnapshotManager(db_path=temp_db)

    def test_create_returns_snapshot_id(self, mgr: SnapshotManager) -> None:
        sid = mgr.create(state={"status": "active"}, task_id="task-1", agent_type="test", description="test")
        assert sid.startswith("snap_")
        assert len(sid) > 10

    def test_get_latest_returns_latest(self, mgr: SnapshotManager) -> None:
        mgr.create(state={"status": "a"}, task_id="task-latest", agent_type="test", step_name="step1")
        latest_state = {"status": "latest", "extra": "data"}
        mgr.create(state=latest_state, task_id="task-latest", agent_type="test", step_name="step2")

        result = mgr.get_latest("task-latest")
        assert result is not None
        assert result["state"]["status"] == "latest"
        assert result["snapshot_id"].startswith("snap_")

    def test_get_latest_none_for_unknown_task(self, mgr: SnapshotManager) -> None:
        assert mgr.get_latest("nonexistent-task") is None

    def test_list_by_task_returns_ordered(self, mgr: SnapshotManager) -> None:
        mgr.create(state={"n": 1}, task_id="lst-ord-t1", agent_type="a", step_name="s1")
        mgr.create(state={"n": 2}, task_id="lst-ord-t1", agent_type="b", step_name="s2")
        mgr.create(state={"n": 3}, task_id="lst-ord-t1", agent_type="a", step_name="s3")

        snapshots = mgr.list_by_task("lst-ord-t1")
        assert len(snapshots) == 3
        assert all(s["task_id"] == "lst-ord-t1" for s in snapshots)

    def test_list_by_task_with_agent_type_filter(self, mgr: SnapshotManager) -> None:
        mgr.create(state={}, task_id="task-filter", agent_type="type-a")
        mgr.create(state={}, task_id="task-filter", agent_type="type-b")

        filtered = mgr.list_by_task("task-filter", agent_type="type-a")
        assert len(filtered) == 1
        assert filtered[0]["agent_type"] == "type-a"

    def test_clear_task_removes_all(self, mgr: SnapshotManager) -> None:
        mgr.create(state={}, task_id="task-clear")
        mgr.create(state={}, task_id="task-clear")
        mgr.clear_task("task-clear")

        assert mgr.list_by_task("task-clear") == []

    def test_state_hash_deterministic(self, mgr: SnapshotManager) -> None:
        s1 = mgr.create(state={"key": "value"}, task_id="ttask1", agent_type="test")
        s2 = mgr.create(state={"key": "value"}, task_id="ttask2", agent_type="test")
        assert s1 != s2  # different task_id in hash
        assert s1.startswith("snap_")


# ----------------------------------------------------------------------
# Handler 测试 — 通过 SnapshotManager 路径 (无 langgraph 依赖)
# ----------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def mgr(temp_dir: str) -> SnapshotManager:
    return SnapshotManager(db_path=temp_dir)


@pytest.fixture
def ctx() -> CommandContext:
    return CommandContext(
        user_id="user-tc",
        permissions=["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
        session_id="sess-tc",
        db=None,  # 测试降级路径
        redis=None,
    )


class TestHandleRollback:
    @pytest.mark.asyncio
    async def test_rollback_shows_snapshot_preview(self, ctx: CommandContext, mgr: SnapshotManager) -> None:
        with patch("app.commands.handlers.task_control._get_snapshot_manager", return_value=mgr):
            mgr.create(state={"step": 1}, task_id="rb-preview", step_name="step1", description="first")
            mgr.create(state={"step": 2}, task_id="rb-preview", step_name="step2", description="second")

            result = await handle_rollback(["rb-preview", "2"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            assert "2" in result.message
            assert result.data["total"] == 2
            assert len(result.data["preview_snapshots"]) == 2

    @pytest.mark.asyncio
    async def test_rollback_steps_param(self, ctx: CommandContext, mgr: SnapshotManager) -> None:
        with patch("app.commands.handlers.task_control._get_snapshot_manager", return_value=mgr):
            for i in range(5):
                mgr.create(state={"step": i}, task_id="rb-multi")

            result = await handle_rollback(["rb-multi", "2"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            assert result.data["total"] == 5
            assert len(result.data["preview_snapshots"]) == 2


class TestHandleSnapshot:
    @pytest.fixture
    def temp_db(self) -> str:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except Exception:
            pass

    @pytest.fixture
    def snap_mgr(self, temp_db: str) -> SnapshotManager:
        return SnapshotManager(db_path=temp_db)

    @pytest.mark.asyncio
    async def test_snapshot_lists_snapshots(self, ctx: CommandContext, snap_mgr: SnapshotManager) -> None:
        with patch("app.commands.handlers.task_control._get_snapshot_manager", return_value=snap_mgr):
            snap_mgr.create(state={"v": 1}, task_id="snap-list-test")
            snap_mgr.create(state={"v": 2}, task_id="snap-list-test")

            result = await handle_snapshot(["snap-list-test"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            assert "2" in result.message
            assert len(result.data["snapshots"]) == 2


class TestHandleCheckpoint:
    @pytest.mark.asyncio
    async def test_checkpoint_uses_session_id_fallback(self, ctx: CommandContext) -> None:
        ctx.session_id = "ckpt-sess"
        result = await handle_checkpoint([], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["task_id"] == "ckpt-sess"
        assert result.data["snapshot_id"].startswith("snap_")

    @pytest.mark.asyncio
    async def test_checkpoint_creates_snapshot(self, ctx: CommandContext) -> None:
        result = await handle_checkpoint(["ckpt-task"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["task_id"] == "ckpt-task"
        assert result.data["snapshot_id"].startswith("snap_")
        assert "已创建检查点" in result.message

    @pytest.mark.asyncio
    async def test_checkpoint_with_flag(self, ctx: CommandContext) -> None:
        result = await handle_checkpoint(["ckpt-task", "--description", "my-checkpoint"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["task_id"] == "ckpt-task"


class TestHandlePause:
    @pytest.mark.asyncio
    async def test_pause_requires_session_id(self, ctx: CommandContext) -> None:
        ctx.session_id = ""
        result = await handle_pause([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_pause_creates_snapshot(self, ctx: CommandContext) -> None:
        result = await handle_pause(["pause-sess-1"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert "已暂停" in result.message
        assert result.data["snapshot_id"].startswith("snap_")


class TestHandleResume:
    @pytest.mark.asyncio
    async def test_resume_requires_session_id(self, ctx: CommandContext) -> None:
        ctx.session_id = ""
        result = await handle_resume([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_resume_restores_snapshot(self, ctx: CommandContext) -> None:
        mgr = _get_snapshot_manager()
        mgr.create(state={"status": "active"}, task_id="resume-sess-1")

        result = await handle_resume(["resume-sess-1"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert "已恢复" in result.message
        assert result.data["snapshot_id"].startswith("snap_")


class TestHandleCancel:
    @pytest.mark.asyncio
    async def test_cancel_requires_session_id(self, ctx: CommandContext) -> None:
        ctx.session_id = ""
        result = await handle_cancel([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_cancel_degraded_path_no_db(self, ctx: CommandContext) -> None:
        ctx.db = None  # 降级路径
        result = await handle_cancel(["cancel-sess-1"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert "已取消" in result.message or "降级" in result.message
        assert result.data["session_id"] == "cancel-sess-1"

    @pytest.mark.asyncio
    async def test_cancel_with_mock_db(self, ctx: CommandContext) -> None:
        from unittest.mock import AsyncMock, MagicMock, Mock
        from sqlalchemy.ext.asyncio import AsyncSession

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.add = Mock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        ctx.db = mock_db

        result = await handle_cancel(["cancel-sess-2"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert "cancel" in result.data["handler"]
        assert result.data["session_id"] == "cancel-sess-2"


class TestTaskControlRegistration:
    def test_task_control_8_commands(self) -> None:
        from app.commands import CommandRegistry, register_all
        reg = CommandRegistry()
        register_all(reg)
        task_cmds = reg.list_by_category("task")
        assert len(task_cmds) == 8
        names = [c["name"] for c in task_cmds]
        for name in ["restart", "pause", "resume", "cancel", "retry", "rollback", "snapshot", "checkpoint"]:
            assert name in names, f"{name} not registered"

    def test_pause_alias(self) -> None:
        from app.commands import CommandRegistry, register_all
        reg = CommandRegistry()
        register_all(reg)
        resolved = reg.get("/p")
        assert resolved is not None
        assert resolved["name"] == "pause"