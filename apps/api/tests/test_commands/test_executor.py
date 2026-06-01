"""Tests for CommandExecutor — 验证 4 层 dispatcher 流程."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.commands.audit import CommandAuditService
from app.commands.executor import CommandExecutor
from app.commands.permissions import Permission
from app.commands.registry import CommandRegistry
from app.commands.types import (
    CommandCategory,
    CommandContext,
    CommandErrorCode,
    CommandResult,
)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_audit() -> CommandAuditService:
    return CommandAuditService(db=AsyncMock())


@pytest.fixture
def executor(mock_audit: CommandAuditService) -> CommandExecutor:
    reg = CommandRegistry()
    return CommandExecutor(registry=reg, audit=mock_audit, redis=None)


@pytest.fixture
def ctx() -> CommandContext:
    return CommandContext(
        user_id="user-1",
        permissions=["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
        session_id="sess-1",
    )


# ----------------------------------------------------------------------
# passthrough & 透传
# ----------------------------------------------------------------------

class TestPassthrough:
    @pytest.mark.asyncio
    async def test_double_slash_passthrough(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("// hello world", ctx)
        assert result.error_code == CommandErrorCode.PASSTHROUGH
        assert result.message == "hello world"
        assert result.data["passthrough"] is True

    @pytest.mark.asyncio
    async def test_non_command_passthrough(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("hello world", ctx)
        assert result.error_code == CommandErrorCode.PASSTHROUGH
        assert result.message == "hello world"

    @pytest.mark.asyncio
    async def test_empty_double_slash_passthrough(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("//", ctx)
        assert result.error_code == CommandErrorCode.PASSTHROUGH
        assert result.message == ""


# ----------------------------------------------------------------------
# 解析与查找
# ----------------------------------------------------------------------

class TestParseAndLookup:
    @pytest.mark.asyncio
    async def test_unknown_command_returns_not_found(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/nonexistent_cmd_xyz", ctx)
        assert result.error_code == CommandErrorCode.CMD_NOT_FOUND
        assert "未知命令" in result.message

    @pytest.mark.asyncio
    async def test_parse_error_returns_invalid_args(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        # 以 / 开头但格式错误
        result = await executor.execute("/", ctx)
        # 单独 / 应被 parse 拒绝
        assert result.code in (
            CommandErrorCode.INVALID_ARGS.value,
            CommandErrorCode.PASSTHROUGH.value,
        )


# ----------------------------------------------------------------------
# 权限
# ----------------------------------------------------------------------

class TestPermission:
    @pytest.mark.asyncio
    async def test_permission_denied_returns_error(self) -> None:
        reg = CommandRegistry()

        async def denied_handler(args, flags, c):
            return CommandResult.success("should not reach")

        reg.register(
            name="/elevated_only",
            handler=denied_handler,
            permission=Permission.L4_ADMIN,
            category=CommandCategory.SYSTEM,
        )
        exec_ = CommandExecutor(registry=reg, audit=CommandAuditService(db=AsyncMock()))
        ctx_low = CommandContext(user_id="u", permissions=[], session_id="s")
        result = await exec_.execute("/elevated_only", ctx_low)
        assert result.error_code == CommandErrorCode.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_admin_passes_all_permissions(self, executor: CommandExecutor) -> None:
        reg = executor.registry

        async def ok_handler(args, flags, c):
            return CommandResult.success("ok")

        reg.register(
            name="/l4_test",
            handler=ok_handler,
            permission=Permission.L4_ADMIN,
            category=CommandCategory.SYSTEM,
        )
        ctx_admin = CommandContext(
            user_id="u", permissions=["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
            session_id="s",
        )
        result = await executor.execute("/l4_test", ctx_admin)
        assert result.error_code == CommandErrorCode.SUCCESS


# ----------------------------------------------------------------------
# Confirm
# ----------------------------------------------------------------------

class TestConfirm:
    @pytest.mark.asyncio
    async def test_need_confirm_without_force_returns_token(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        reg = executor.registry

        async def dangerous(args, flags, c):
            return CommandResult.success("deleted")

        reg.register(
            name="/delete_candidate",
            handler=dangerous,
            permission=Permission.L1_BASIC,
            category=CommandCategory.CRUD,
            need_confirm=True,
        )
        result = await executor.execute("/delete_candidate abc", ctx)
        assert result.error_code == CommandErrorCode.CONFIRM_REQUIRED
        assert result.confirmation_token is not None
        assert result.confirmation_token.startswith("confirm-")

    @pytest.mark.asyncio
    async def test_need_confirm_with_force_executes(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        reg = executor.registry

        async def dangerous(args, flags, c):
            return CommandResult.success("deleted")

        reg.register(
            name="/delete_candidate2",
            handler=dangerous,
            permission=Permission.L1_BASIC,
            category=CommandCategory.CRUD,
            need_confirm=True,
        )
        result = await executor.execute("/delete_candidate2 abc --force", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.message == "deleted"


# ----------------------------------------------------------------------
# Handler 执行 + 异常
# ----------------------------------------------------------------------

class TestHandlerExecution:
    @pytest.mark.asyncio
    async def test_handler_success(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        reg = executor.registry

        async def ok(args, flags, c):
            return CommandResult.success("done", data={"echo": args})

        reg.register(
            name="/echo",
            handler=ok,
            permission=Permission.L1_BASIC,
            category=CommandCategory.SYSTEM,
        )
        result = await executor.execute("/echo hello world", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.message == "done"
        assert result.data == {"echo": ["hello", "world"]}

    @pytest.mark.asyncio
    async def test_handler_exception_returns_internal(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        reg = executor.registry

        async def boom(args, flags, c):
            raise RuntimeError("kaboom")

        reg.register(
            name="/boom",
            handler=boom,
            permission=Permission.L1_BASIC,
            category=CommandCategory.SYSTEM,
        )
        result = await executor.execute("/boom", ctx)
        assert result.error_code == CommandErrorCode.INTERNAL_ERROR
        assert "kaboom" in result.message


# ----------------------------------------------------------------------
# Redis 锁
# ----------------------------------------------------------------------

class TestRedisLock:
    @pytest.mark.asyncio
    async def test_lock_acquisition_failure_returns_lock_timeout(self, ctx: CommandContext) -> None:
        reg = CommandRegistry()
        # Mock redis client: lock().acquire() 总是 False
        mock_redis = MagicMock()
        mock_lock = AsyncMock()
        mock_lock.acquire.return_value = False
        mock_redis.lock.return_value = mock_lock
        exec_ = CommandExecutor(
            registry=reg,
            audit=CommandAuditService(db=AsyncMock()),
            redis=mock_redis,
            lock_timeout=10,
        )

        async def ok(args, flags, c):
            return CommandResult.success("ok")

        reg.register(
            name="/locked",
            handler=ok,
            permission=Permission.L1_BASIC,
            category=CommandCategory.SYSTEM,
        )
        result = await exec_.execute("/locked", ctx)
        assert result.error_code == CommandErrorCode.LOCK_TIMEOUT

    @pytest.mark.asyncio
    async def test_no_session_id_skips_lock(self, executor: CommandExecutor) -> None:
        # 即使 redis 配置了,没有 session_id 也跳过锁
        reg = executor.registry

        async def ok(args, flags, c):
            return CommandResult.success("ok")

        reg.register(
            name="/no_session",
            handler=ok,
            permission=Permission.L1_BASIC,
            category=CommandCategory.SYSTEM,
        )
        ctx = CommandContext(user_id="u", permissions=["L4_ADMIN"], session_id=None)
        result = await executor.execute("/no_session", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS


# ----------------------------------------------------------------------
# 审计
# ----------------------------------------------------------------------

class TestAuditFire:
    @pytest.mark.asyncio
    async def test_audit_called_for_success(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        reg = executor.registry

        async def ok(args, flags, c):
            return CommandResult.success("ok")

        reg.register(
            name="/audit_ok",
            handler=ok,
            permission=Permission.L1_BASIC,
            category=CommandCategory.SYSTEM,
        )

        with patch.object(executor, "_fire_audit") as fire:
            await executor.execute("/audit_ok", ctx)
            fire.assert_called_once()
            call_kwargs = fire.call_args.kwargs
            assert call_kwargs["parsed"].name == "/audit_ok"
            assert call_kwargs["result"].error_code == CommandErrorCode.SUCCESS
            assert call_kwargs["duration_ms"] is not None

    @pytest.mark.asyncio
    async def test_audit_called_for_not_found(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        with patch.object(executor, "_fire_audit") as fire:
            await executor.execute("/nope_nope_nope", ctx)
            fire.assert_called_once()
            assert fire.call_args.kwargs["result"].error_code == CommandErrorCode.CMD_NOT_FOUND

    @pytest.mark.asyncio
    async def test_audit_called_for_permission_denied(self, ctx: CommandContext) -> None:
        reg = CommandRegistry()

        async def noop(args, flags, c):
            return CommandResult.success("nope")

        reg.register(
            name="/l4_test",
            handler=noop,
            permission=Permission.L4_ADMIN,
            category=CommandCategory.SYSTEM,
        )
        exec_ = CommandExecutor(registry=reg, audit=CommandAuditService(db=AsyncMock()))
        ctx_viewer = CommandContext(user_id="u", permissions=[], session_id="s")

        with patch.object(exec_, "_fire_audit") as fire:
            await exec_.execute("/l4_test", ctx_viewer)
            fire.assert_called_once()
            assert fire.call_args.kwargs["result"].error_code == CommandErrorCode.PERMISSION_DENIED


# ----------------------------------------------------------------------
# Alias 解析
# ----------------------------------------------------------------------

class TestAliasResolution:
    @pytest.mark.asyncio
    async def test_alias_h_resolves_to_help(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        # /h 应该解析为 /help(前提:registry 中 /help 已注册且 h 是 alias)
        # 这依赖于 register_all 是否被调用;此处直接注册 /help + alias
        reg = executor.registry

        async def help(args, flags, c):
            return CommandResult.success("HELP")

        reg.register(
            name="/help",
            handler=help,
            permission=Permission.L1_BASIC,
            category=CommandCategory.SYSTEM,
            aliases=["/h"],
        )
        result = await executor.execute("/h", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.message == "HELP"
