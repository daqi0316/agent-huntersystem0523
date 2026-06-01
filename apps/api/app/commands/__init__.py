"""Commands package — AI 招聘 Agent 内置命令系统 V2.0 公开 API.

V.1 阶段导出:
- types: CommandContext, CommandResult, ParsedCommand, CommandErrorCode, CommandCategory
- parser: CommandParser
- permissions: Permission, has_permission, require_permission, check_permission
- registry: CommandRegistry
- audit: CommandAuditService, fire_and_forget
- executor: CommandExecutor
- handlers: 4 个分类, 共 28 个命令

公开函数:
- register_all(registry)  — 把全部 28 个命令注册到给定 registry
- get_default_executor()  — 装配默认 executor(供 FastAPI 依赖注入复用)
"""

from __future__ import annotations

from app.commands.audit import CommandAuditService, fire_and_forget
from app.commands.executor import CommandExecutor
from app.commands.handlers.crud import CRUD_COMMANDS
from app.commands.handlers.dialog import DIALOG_COMMANDS
from app.commands.handlers.system_ops import SYSTEM_COMMANDS
from app.commands.handlers.task_control import TASK_CONTROL_COMMANDS
from app.commands.parser import CommandParser
from app.commands.permissions import (
    Permission,
    check_permission,
    has_permission,
    require_permission,
    role_to_permissions,
)
from app.commands.registry import CommandRegistry
from app.commands.types import (
    CommandCategory,
    CommandContext,
    CommandErrorCode,
    CommandResult,
    ParsedCommand,
)

__all__ = [
    # types
    "CommandCategory",
    "CommandContext",
    "CommandErrorCode",
    "CommandResult",
    "ParsedCommand",
    # parser
    "CommandParser",
    # permissions
    "Permission",
    "check_permission",
    "has_permission",
    "require_permission",
    "role_to_permissions",
    # registry
    "CommandRegistry",
    # audit
    "CommandAuditService",
    "fire_and_forget",
    # executor
    "CommandExecutor",
    # 全部 28 命令注册清单
    "TASK_CONTROL_COMMANDS",
    "DIALOG_COMMANDS",
    "CRUD_COMMANDS",
    "SYSTEM_COMMANDS",
    # 公开函数
    "register_all",
    "get_default_executor",
    "COMMAND_COUNT",
]


COMMAND_COUNT = 31


def register_all(registry: CommandRegistry) -> CommandRegistry:
    """把 4 类共 28 个命令注册到给定 registry.

    幂等:重复调用会先清空再注册.
    """
    registry.clear()
    for cmd in (
        *TASK_CONTROL_COMMANDS,
        *DIALOG_COMMANDS,
        *CRUD_COMMANDS,
        *SYSTEM_COMMANDS,
    ):
        registry.register(**cmd)
    return registry


def get_default_executor(
    redis_client=None,
    audit: CommandAuditService | None = None,
    lock_timeout: int = 10,
) -> CommandExecutor:
    """装配一个默认 executor — 包含全部 28 命令 + 默认 audit service.

    FastAPI 端使用:
        @app.post("/commands")
        async def run(cmd: CommandRequest, db: AsyncSession = Depends(get_db)):
            executor = get_default_executor(audit=CommandAuditService(db=db))
            return await executor.execute(cmd.input, ctx)
    """
    registry = CommandRegistry()
    register_all(registry)
    return CommandExecutor(
        registry=registry,
        audit=audit or CommandAuditService(),
        redis=redis_client,
        lock_timeout=lock_timeout,
    )
