"""Tests for dialog command handlers — V.3 真实实现.

验证 8 个 handler:
- /new        → create_session + Redis current/previous tracking
- /history   → list_sessions + message count
- /switch    → Redis current/previous switch
- /back      → Redis previous → current
- /clear     → delete_session (cascade deletes messages)
- /fork      → new session + copy all messages
- /merge     → add source messages to target session
- /diff      → content-level diff between two sessions
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.commands import (
    CommandCategory,
    CommandContext,
    CommandErrorCode,
    CommandExecutor,
    CommandRegistry,
    CommandAuditService,
    register_all,
)
from app.commands.handlers.dialog import (
    handle_new,
    handle_history,
    handle_switch,
    handle_back,
    handle_clear,
    handle_fork,
    handle_merge,
    handle_diff,
)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def mock_db() -> AsyncMock:
    from unittest.mock import MagicMock
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def executor(mock_db: AsyncMock) -> CommandExecutor:
    reg = CommandRegistry()
    register_all(reg)
    return CommandExecutor(
        registry=reg,
        audit=CommandAuditService(db=mock_db),
        redis=None,
    )


@pytest.fixture
def ctx(mock_db: AsyncMock) -> CommandContext:
    return CommandContext(
        user_id="user-dialog",
        permissions=["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
        session_id="sess-dialog",
        db=mock_db,
    )


@pytest.fixture
def ctx_no_db() -> CommandContext:
    return CommandContext(
        user_id="user-dialog",
        permissions=["L1_BASIC"],
        session_id="sess-dialog",
        db=None,
        redis=None,
    )


@pytest.fixture
def mock_redis() -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    return r


# ----------------------------------------------------------------------
# /new
# ----------------------------------------------------------------------

class TestHandleNew:
    @pytest.mark.asyncio
    async def test_new_without_db_returns_not_implemented(self, ctx_no_db: CommandContext) -> None:
        result = await handle_new([], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED
        assert "数据库未就绪" in result.message

    @pytest.mark.asyncio
    async def test_new_creates_session(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService
        mock_session = MagicMock()
        mock_session.id = "new-session-123"
        mock_session.title = "新对话"

        with patch.object(ConversationService, "create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_session
            result = await handle_new([], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            mock_create.assert_called_once_with("user-dialog", title="新对话")
            assert "new-session-123" in result.data["session_id"]

    @pytest.mark.asyncio
    async def test_new_uses_custom_title(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService
        mock_session = MagicMock()
        mock_session.id = "sess-custom"
        mock_session.title = "我的招聘任务"

        with patch.object(ConversationService, "create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_session
            result = await handle_new(["我的招聘任务"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            mock_create.assert_called_once_with("user-dialog", title="我的招聘任务")


# ----------------------------------------------------------------------
# /history
# ----------------------------------------------------------------------

class TestHandleHistory:
    @pytest.mark.asyncio
    async def test_history_without_db_returns_not_implemented(self, ctx_no_db: CommandContext) -> None:
        result = await handle_history([], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_history_returns_sessions(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService
        from datetime import datetime, timezone

        mock_sessions = [
            MagicMock(
                id=f"sess-{i}",
                title=f"会话 {i}",
                updated_at=datetime.now(timezone.utc),
            )
            for i in range(3)
        ]

        with patch.object(ConversationService, "list_sessions", new_callable=AsyncMock) as mock_list, \
             patch.object(ConversationService, "get_session_message_count", new_callable=AsyncMock) as mock_count:
            mock_list.return_value = mock_sessions
            mock_count.return_value = 5

            result = await handle_history([], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            assert len(result.data["sessions"]) == 3
            assert result.data["sessions"][0]["message_count"] == 5
            assert result.data["handler"] == "history"

    @pytest.mark.asyncio
    async def test_history_respects_limit_arg(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService
        mock_sessions = [MagicMock(id=f"sess-{i}", title=f"s{i}", updated_at=None) for i in range(10)]

        with patch.object(ConversationService, "list_sessions", new_callable=AsyncMock) as mock_list, \
             patch.object(ConversationService, "get_session_message_count", new_callable=AsyncMock) as mock_count:
            mock_list.return_value = mock_sessions
            mock_count.return_value = 0
            result = await handle_history(["5"], {}, ctx)

            mock_list.assert_called_once_with("user-dialog", limit=5, offset=0)


# ----------------------------------------------------------------------
# /switch
# ----------------------------------------------------------------------

class TestHandleSwitch:
    @pytest.mark.asyncio
    async def test_switch_requires_session_id(self, ctx: CommandContext) -> None:
        result = await handle_switch([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "session_id" in result.message

    @pytest.mark.asyncio
    async def test_switch_updates_redis(self, ctx: CommandContext, mock_redis: AsyncMock) -> None:
        ctx.redis = mock_redis
        ctx.session_id = "current-sess"

        result = await handle_switch(["target-sess"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["session_id"] == "target-sess"
        assert result.data["previous_id"] == "current-sess"
        assert mock_redis.set.call_count >= 1

    @pytest.mark.asyncio
    async def test_switch_without_redis_succeeds(self, ctx: CommandContext) -> None:
        ctx.redis = None
        ctx.db = None

        result = await handle_switch(["any-sess"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert "切换" in result.message


# ----------------------------------------------------------------------
# /back
# ----------------------------------------------------------------------

class TestHandleBack:
    @pytest.mark.asyncio
    async def test_back_without_redis_returns_not_implemented(self, ctx_no_db: CommandContext) -> None:
        result = await handle_back([], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED
        assert "Redis" in result.message

    @pytest.mark.asyncio
    async def test_back_returns_previous_session(self, ctx: CommandContext, mock_redis: AsyncMock) -> None:
        mock_redis.get = AsyncMock(side_effect=[
            "previous-sess-456",  # _PREVIOUS_KEY
            "current-sess-123",  # _CURRENT_KEY
        ])
        ctx.redis = mock_redis

        result = await handle_back([], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["session_id"] == "previous-sess-456"

    @pytest.mark.asyncio
    async def test_back_no_previous(self, ctx: CommandContext, mock_redis: AsyncMock) -> None:
        mock_redis.get = AsyncMock(return_value=None)
        ctx.redis = mock_redis

        result = await handle_back([], {}, ctx)

        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "没有上一个会话" in result.message


# ----------------------------------------------------------------------
# /clear
# ----------------------------------------------------------------------

class TestHandleClear:
    @pytest.mark.asyncio
    async def test_clear_without_db_returns_not_implemented(self, ctx_no_db: CommandContext) -> None:
        result = await handle_clear([], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_clear_uses_context_session_id(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService

        with patch.object(ConversationService, "get_session_message_count", new_callable=AsyncMock) as mock_count, \
             patch.object(ConversationService, "delete_session", new_callable=AsyncMock) as mock_delete:
            mock_count.return_value = 10
            mock_delete.return_value = True

            result = await handle_clear([], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            mock_count.assert_called_once_with("sess-dialog")
            mock_delete.assert_called_once_with("sess-dialog")
            assert result.data["message_count"] == 10

    @pytest.mark.asyncio
    async def test_clear_with_explicit_session_id(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService

        with patch.object(ConversationService, "get_session_message_count", new_callable=AsyncMock) as mock_count, \
             patch.object(ConversationService, "delete_session", new_callable=AsyncMock) as mock_delete:
            mock_count.return_value = 3
            mock_delete.return_value = True

            result = await handle_clear(["other-session"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            mock_count.assert_called_once_with("other-session")
            mock_delete.assert_called_once_with("other-session")


# ----------------------------------------------------------------------
# /fork
# ----------------------------------------------------------------------

class TestHandleFork:
    @pytest.mark.asyncio
    async def test_fork_requires_source_id(self, ctx: CommandContext) -> None:
        result = await handle_fork([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "source_session_id" in result.message

    @pytest.mark.asyncio
    async def test_fork_without_db_returns_not_implemented(self, ctx_no_db: CommandContext) -> None:
        result = await handle_fork(["source-sess"], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_fork_copies_messages(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService
        from datetime import datetime, timezone

        mock_source = MagicMock(id="source-123", title="原始会话", updated_at=datetime.now(timezone.utc))
        mock_new = MagicMock(id="new-fork-456", title="会话副本", updated_at=datetime.now(timezone.utc))

        mock_msgs = [
            MagicMock(role="user", content="Hello", tool_calls=None, tool_result=None),
            MagicMock(role="assistant", content="Hi there", tool_calls=None, tool_result=None),
        ]

        with patch.object(ConversationService, "get_session", new_callable=AsyncMock) as mock_get, \
             patch.object(ConversationService, "create_session", new_callable=AsyncMock) as mock_create, \
             patch.object(ConversationService, "get_history", new_callable=AsyncMock) as mock_hist, \
             patch.object(ConversationService, "add_messages", new_callable=AsyncMock) as mock_add:
            mock_get.return_value = mock_source
            mock_create.return_value = mock_new
            mock_hist.return_value = mock_msgs
            mock_add.return_value = []

            result = await handle_fork(["source-123"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            assert result.data["source_id"] == "source-123"
            assert result.data["new_session_id"] == "new-fork-456"
            assert result.data["message_count"] == 2
            mock_add.assert_called_once()
            copied = mock_add.call_args[0][0]
            assert len(copied) == 2
            assert copied[0]["session_id"] == "new-fork-456"

    @pytest.mark.asyncio
    async def test_fork_nonexistent_source(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService

        with patch.object(ConversationService, "get_session", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle_fork(["does-not-exist"], {}, ctx)

            assert result.error_code == CommandErrorCode.INVALID_ARGS
            assert "不存在" in result.message


# ----------------------------------------------------------------------
# /merge
# ----------------------------------------------------------------------

class TestHandleMerge:
    @pytest.mark.asyncio
    async def test_merge_requires_two_args(self, ctx: CommandContext) -> None:
        result = await handle_merge(["only-one"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_merge_without_db_returns_not_implemented(self, ctx_no_db: CommandContext) -> None:
        result = await handle_merge(["a", "b"], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_merge_adds_messages_to_target(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService
        from datetime import datetime, timezone

        mock_src = MagicMock(id="src", title="src", updated_at=datetime.now(timezone.utc))
        mock_tgt = MagicMock(id="tgt", title="tgt", updated_at=datetime.now(timezone.utc))

        mock_msgs = [
            MagicMock(role="user", content="merged msg", tool_calls=None, tool_result=None),
        ]

        with patch.object(ConversationService, "get_session", new_callable=AsyncMock) as mock_get, \
             patch.object(ConversationService, "get_history", new_callable=AsyncMock) as mock_hist, \
             patch.object(ConversationService, "add_messages", new_callable=AsyncMock) as mock_add:
            mock_get.side_effect = [mock_src, mock_tgt]
            mock_hist.return_value = mock_msgs
            mock_add.return_value = []

            result = await handle_merge(["src", "tgt"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            assert result.data["count"] == 1
            mock_add.assert_called_once()
            merged = mock_add.call_args[0][0]
            assert merged[0]["session_id"] == "tgt"

    @pytest.mark.asyncio
    async def test_merge_empty_source(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService
        from datetime import datetime, timezone

        mock_src = MagicMock(id="empty-src", title="empty", updated_at=datetime.now(timezone.utc))
        mock_tgt = MagicMock(id="tgt", title="tgt", updated_at=datetime.now(timezone.utc))

        with patch.object(ConversationService, "get_session", new_callable=AsyncMock) as mock_get, \
             patch.object(ConversationService, "get_history", new_callable=AsyncMock) as mock_hist:
            mock_get.side_effect = [mock_src, mock_tgt]
            mock_hist.return_value = []

            result = await handle_merge(["empty-src", "tgt"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            assert result.data["count"] == 0


# ----------------------------------------------------------------------
# /diff
# ----------------------------------------------------------------------

class TestHandleDiff:
    @pytest.mark.asyncio
    async def test_diff_requires_two_args(self, ctx: CommandContext) -> None:
        result = await handle_diff(["only-one"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_diff_without_db_returns_not_implemented(self, ctx_no_db: CommandContext) -> None:
        result = await handle_diff(["a", "b"], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_diff_finds_unique_messages(self, ctx: CommandContext) -> None:
        from app.services.conversation_service import ConversationService

        msgs_a = [
            MagicMock(role="user", content="msg A1"),
            MagicMock(role="assistant", content="msg A2"),
            MagicMock(role="user", content="shared"),
        ]
        msgs_b = [
            MagicMock(role="user", content="msg B1"),
            MagicMock(role="assistant", content="shared"),
        ]

        with patch.object(ConversationService, "get_history", new_callable=AsyncMock) as mock_hist:
            mock_hist.side_effect = [msgs_a, msgs_b]

            result = await handle_diff(["sess-a", "sess-b"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            assert result.data["a_count"] == 3
            assert result.data["b_count"] == 2
            assert "msg A1" in result.data["only_in_a"]
            assert "msg A2" in result.data["only_in_a"]
            assert "msg B1" in result.data["only_in_b"]
            assert "shared" not in result.data["only_in_a"]
            assert "shared" not in result.data["only_in_b"]
            assert result.data["only_in_a"] == ["msg A1", "msg A2"]  # order preserved


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------

class TestDialogRegistration:
    def test_all_8_commands_registered(self) -> None:
        from app.commands import CommandRegistry, register_all
        reg = CommandRegistry()
        register_all(reg)
        dialog_cmds = reg.list_by_category("dialog")
        assert len(dialog_cmds) == 8

    def test_new_has_n_alias(self) -> None:
        from app.commands import CommandRegistry, register_all
        reg = CommandRegistry()
        register_all(reg)
        resolved = reg.get("/n")
        assert resolved is not None
        assert resolved["name"] == "new"

    def test_handler_module_name(self) -> None:
        from app.commands import CommandRegistry, register_all
        reg = CommandRegistry()
        register_all(reg)
        cmd = reg.get("/new")
        assert cmd is not None
        assert cmd["category"] == CommandCategory.DIALOG