"""V.5 system_ops handlers tests — /settings /export /import."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.commands.executor import CommandExecutor
from app.commands.handlers.system_ops import (
    handle_export,
    handle_help,
    handle_import,
    handle_settings,
    handle_status,
    handle_version,
)
from app.commands.registry import CommandRegistry
from app.commands.types import CommandContext, CommandErrorCode
from app.commands.audit import CommandAuditService


@pytest.fixture
def ctx() -> CommandContext:
    return CommandContext(
        user_id="user-test",
        permissions=["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
        session_id="sess-v5",
    )


@pytest.fixture
def executor() -> CommandExecutor:
    from app.commands.registry import register_all

    reg = CommandRegistry()
    register_all(reg)
    return CommandExecutor(
        registry=reg,
        audit=CommandAuditService(db=AsyncMock()),
        redis=None,
    )


class TestHandleSettings:
    async def test_settings_no_args_lists_empty(self, ctx: CommandContext) -> None:
        result = await handle_settings([], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "偏好设置" in result.message
        assert result.data["settings"] == {}

    async def test_settings_key_query(self, ctx: CommandContext) -> None:
        ctx.extra = {"user_settings": {"theme": "dark"}}
        result = await handle_settings(["theme"], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "dark" in result.message

    async def test_settings_key_query_unset(self, ctx: CommandContext) -> None:
        result = await handle_settings(["missing"], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "(未设置)" in result.message

    async def test_settings_set_value(self, ctx: CommandContext) -> None:
        result = await handle_settings(["theme", "light"], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "light" in result.message
        assert ctx.extra["user_settings"]["theme"] == "light"

    async def test_settings_set_multiple_words(self, ctx: CommandContext) -> None:
        result = await handle_settings(["greeting", "hello world"], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert ctx.extra["user_settings"]["greeting"] == "hello world"

    async def test_executor_settings(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/settings", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS


class TestHandleExport:
    async def test_export_config_success(self, ctx: CommandContext) -> None:
        result = await handle_export([], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "config" in result.data["export_type"]

    async def test_export_explicit_type(self, ctx: CommandContext) -> None:
        result = await handle_export(["config"], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["export_type"] == "config"

    async def test_export_invalid_type(self, ctx: CommandContext) -> None:
        result = await handle_export(["invalid"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "不支持" in result.message

    async def test_export_commands_no_audit(self, ctx: CommandContext) -> None:
        result = await handle_export(["commands"], {}, ctx)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED
        assert "审计服务" in result.message

    async def test_export_commands_with_audit(self, ctx: CommandContext) -> None:
        mock_audit = AsyncMock()
        mock_rec = MagicMock()
        mock_rec.command_name = "/help"
        mock_rec.result_code = "success"
        mock_rec.created_at = None
        mock_audit.list_recent = AsyncMock(return_value=[mock_rec])
        ctx.extra = {"audit_service": mock_audit}

        result = await handle_export(["commands"], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["payload"]["count"] == 1

    async def test_export_sessions_no_db(self, ctx: CommandContext) -> None:
        result = await handle_export(["sessions"], {}, ctx)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED
        assert "数据库" in result.message

    async def test_executor_export(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/export config", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS


class TestHandleImport:
    async def test_import_no_args(self, ctx: CommandContext) -> None:
        result = await handle_import([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    async def test_import_invalid_json(self, ctx: CommandContext) -> None:
        result = await handle_import(["not json"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "JSON" in result.message

    async def test_import_valid_json_preview(self, ctx: CommandContext) -> None:
        result = await handle_import(['{"settings":{"theme":"dark"}}'], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["requires_force"] is True
        assert result.data["preview"]["settings"]["theme"] == "dark"

    async def test_import_force_mode(self, ctx: CommandContext) -> None:
        result = await handle_import(
            ['{"settings":{"theme":"dark"}}'],
            {"force": True},
            ctx,
        )
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "force" in result.message.lower()

    async def test_import_with_sessions_preview(self, ctx: CommandContext) -> None:
        result = await handle_import(
            ['{"sessions":[{"id":1},{"id":2},{"id":3}]}'],
            {},
            ctx,
        )
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["preview"]["sessions"]["count"] == 3

    async def test_executor_import_shows_preview(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute('/import {"settings":{}} --force', ctx)
        assert result.error_code == CommandErrorCode.SUCCESS


class TestHelpVersionStatus:
    async def test_help_returns_31_commands(self, ctx: CommandContext) -> None:
        result = await handle_help([], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["command_count"] == 31
        assert result.data["categories"] == 4

    async def test_version_returns_v2(self, ctx: CommandContext) -> None:
        result = await handle_version([], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["version"] == "2.0.0"
        assert "v2" in result.message

    async def test_status_returns_running(self, ctx: CommandContext) -> None:
        result = await handle_status([], {}, ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["status"] == "running"

    async def test_executor_help(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/help", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
        assert "31" in result.message

    async def test_executor_version(self, executor: CommandExecutor, ctx: CommandContext) -> None:
        result = await executor.execute("/version", ctx)
        assert result.error_code == CommandErrorCode.SUCCESS
