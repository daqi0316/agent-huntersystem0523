"""E2E smoke test for /help — V.1 退出标准.

验证:
1. /help 输出含 31 个命令名
2. /help 输出按 4 类分组
3. /help 输出含 7 个 alias
4. /h alias 解析到 /help
5. 整条链路: register_all → executor → /help 真实输出
6. executor 与 audit 真实集成
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.commands import (
    COMMAND_COUNT,
    CommandContext,
    CommandErrorCode,
    CommandExecutor,
    CommandRegistry,
    CommandAuditService,
    register_all,
)


# ----------------------------------------------------------------------
# 注册与数量
# ----------------------------------------------------------------------

class TestRegisterAll:
    def test_register_all_returns_31_commands(self) -> None:
        reg = CommandRegistry()
        register_all(reg)
        assert reg.count() == 31

    def test_register_all_idempotent(self) -> None:
        reg = CommandRegistry()
        register_all(reg)
        register_all(reg)
        assert reg.count() == 31

    def test_command_count_constant(self) -> None:
        assert COMMAND_COUNT == 31


# ----------------------------------------------------------------------
# /help 端到端
# ----------------------------------------------------------------------

class TestHelpEndToEnd:
    @pytest.fixture
    def executor(self) -> CommandExecutor:
        reg = CommandRegistry()
        register_all(reg)
        return CommandExecutor(
            registry=reg,
            audit=CommandAuditService(db=AsyncMock()),
            redis=None,
        )

    @pytest.fixture
    def ctx(self) -> CommandContext:
        return CommandContext(
            user_id="user-1",
            permissions=["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
            session_id="sess-help",
        )

    @pytest.mark.asyncio
    async def test_help_returns_success(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/help", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "招聘 Agent" in result.message
        assert "31" in result.message

    @pytest.mark.asyncio
    async def test_help_lists_all_31_commands(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/help", ctx)
        expected_commands = [
            # TASK
            "/restart", "/pause", "/resume", "/cancel",
            "/retry", "/rollback", "/snapshot", "/checkpoint",
            # DIALOG
            "/new", "/history", "/switch", "/back",
            "/clear", "/merge", "/fork", "/diff",
            # CRUD
            "/read", "/list", "/search", "/write",
            "/add", "/delete", "/batch",
            # SYSTEM
            "/help", "/status", "/version", "/debug", "/config",
            "/settings", "/export", "/import",
        ]
        for cmd in expected_commands:
            assert cmd in result.message, f"/help 输出缺少命令: {cmd}"

    @pytest.mark.asyncio
    async def test_help_groups_4_categories(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/help", ctx)
        assert "任务控制" in result.message
        assert "对话管理" in result.message
        assert "增删改查" in result.message
        assert "系统" in result.message

    @pytest.mark.asyncio
    async def test_help_lists_7_aliases(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/help", ctx)
        for alias in ["/r", "/p", "/s", "/h", "/n", "/l", "/d"]:
            assert alias in result.message, f"/help 输出缺少 alias: {alias}"

    @pytest.mark.asyncio
    async def test_h_alias_resolves_to_help(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/h", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "招聘 Agent" in result.message

    @pytest.mark.asyncio
    async def test_help_returns_data_with_count(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/help", ctx)
        assert result.data is not None
        assert result.data["command_count"] == 31
        assert result.data["categories"] == 4


# ----------------------------------------------------------------------
# 其他系统命令的真实实现
# ----------------------------------------------------------------------

class TestSystemCommandsReal:
    @pytest.fixture
    def executor(self) -> CommandExecutor:
        reg = CommandRegistry()
        register_all(reg)
        return CommandExecutor(
            registry=reg,
            audit=CommandAuditService(db=AsyncMock()),
            redis=None,
        )

    @pytest.fixture
    def ctx(self) -> CommandContext:
        return CommandContext(
            user_id="user-sys",
            permissions=["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
            session_id="sess-sys",
        )

    @pytest.mark.asyncio
    async def test_status_returns_running(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/status", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "运行中" in result.message
        assert result.data["user_id"] == "user-sys"

    @pytest.mark.asyncio
    async def test_status_alias_s(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/s", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "运行中" in result.message

    @pytest.mark.asyncio
    async def test_version_returns_v2(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/version", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "v2" in result.message
        assert result.data["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_config_shows_v2_info(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/config", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "V.2" in result.message
        assert "10s" in result.message  # 锁超时

    @pytest.mark.asyncio
    async def test_debug_without_audit_service(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/debug", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "审计服务未配置" in result.message

    @pytest.mark.asyncio
    async def test_debug_alias_d(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/d", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS

    @pytest.mark.asyncio
    async def test_debug_with_audit_service(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        """Test /debug with audit_service injected via extra."""
        mock_audit = AsyncMock()
        mock_record = MagicMock()
        mock_record.created_at = MagicMock()
        mock_record.created_at.__format__ = MagicMock(return_value="2025-01-01 12:00:00")
        mock_record.command_name = "/help"
        mock_record.result_code = "success"
        mock_audit.list_recent = AsyncMock(return_value=[mock_record])
        ctx.extra = {"audit_service": mock_audit}

        result = await executor.execute("/debug", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["audit_available"] is True
        assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_debug_audit_exception(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        """Test /debug gracefully handles audit service exception."""
        mock_audit = AsyncMock()
        mock_audit.list_recent = AsyncMock(side_effect=RuntimeError("audit failed"))
        ctx.extra = {"audit_service": mock_audit}

        result = await executor.execute("/debug", ctx)
        assert result.error_code == CommandErrorCode.INTERNAL_ERROR
        assert "审计失败" in result.message


# ----------------------------------------------------------------------
# Stub 路径
# ----------------------------------------------------------------------

class TestStubCommands:
    @pytest.fixture
    def executor(self) -> CommandExecutor:
        reg = CommandRegistry()
        register_all(reg)
        return CommandExecutor(
            registry=reg,
            audit=CommandAuditService(db=AsyncMock()),
            redis=None,
        )

    @pytest.fixture
    def ctx(self) -> CommandContext:
        return CommandContext(
            user_id="u",
            permissions=["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
            session_id="s",
        )

    @pytest.mark.asyncio
    async def test_restart_returns_not_implemented(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/restart", ctx)
        # /restart 是 need_confirm, 先返回 confirm_required
        assert result.error_code == CommandErrorCode.CONFIRM_REQUIRED

    @pytest.mark.asyncio
    async def test_restart_with_force_executes(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/restart --force", ctx)
        # 当前测试环境无编排图 + 无 DB, handler 返回 NOT_IMPLEMENTED
        # 生产环境 orchestrator graph 就绪后返回 SUCCESS
        assert result.error_code in (
            CommandErrorCode.SUCCESS,
            CommandErrorCode.NOT_IMPLEMENTED,
        ), f"意外 error_code: {result.error_code}"
        if result.error_code == CommandErrorCode.SUCCESS:
            assert "已重新开始" in result.message or "已创建" in result.message

    @pytest.mark.asyncio
    async def test_restart_with_db_mock(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        """mock context.db 验证 ConversationService 降级路径."""
        import app.commands.handlers.task_control as tc
        from sqlalchemy.ext.asyncio import AsyncSession
        from unittest.mock import AsyncMock, MagicMock, patch

        tc._orchestrator_graph = None

        mock_db = AsyncMock(spec=AsyncSession)
        ctx.db = mock_db
        mock_db.add = Mock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch("app.graphs.orchestrator_graph.create_orchestrator_graph", side_effect=RuntimeError("no graph")):
            result = await executor.execute("/restart --force", ctx)
            assert result.error_code == CommandErrorCode.SUCCESS
            assert "降级" in result.message

    @pytest.mark.asyncio
    async def test_new_command_in_help(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/new", ctx)
        assert result.error_code in (CommandErrorCode.SUCCESS, CommandErrorCode.NOT_IMPLEMENTED)
        assert "新会话" in result.message or "不可用" in result.message

    @pytest.mark.asyncio
    async def test_list_command(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/list candidates", ctx)
        assert result.error_code in (CommandErrorCode.SUCCESS, CommandErrorCode.NOT_IMPLEMENTED)

    @pytest.mark.asyncio
    async def test_unknown_command(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/nope", ctx)
        assert result.error_code == CommandErrorCode.CMD_NOT_FOUND
        assert "/help" in result.message  # 提示用户用 /help
