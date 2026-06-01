"""Command system core types — V.1 基础骨架.

Defines the type contracts used across parser / registry / executor / handlers:
- CommandCategory: 4 大分类（任务控制 / 对话管理 / 数据CRUD / 系统操作）
- CommandErrorCode: 统一错误码，供前端 toast / SSE 事件判断
- ParsedCommand: 解析后的命令中间表示
- CommandContext: 执行上下文（session / user / 权限 / flags）
- CommandResult: 执行结果（success / action / message / data）
- CommandHandler: handler 协议
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


# ── 分类与错误码 ──────────────────────────────────────────


class CommandCategory(str, enum.Enum):
    """命令分类 — 与 V2.0 设计文档 §1 一致."""

    TASK = "task"          # 任务控制（/restart /pause /resume ...）
    DIALOG = "dialog"      # 对话管理（/new /history /switch ...）
    CRUD = "crud"          # 数据 CRUD（/read /list /write /delete ...）
    SYSTEM = "system"      # 系统操作（/help /status /debug /config ...）


class CommandErrorCode(str, enum.Enum):
    """命令执行统一错误码 — 供前端 toast + SSE 事件 type 字段使用."""

    # 解析阶段
    INVALID_INPUT = "invalid_input"            # 空 / 非字符串
    INVALID_SYNTAX = "invalid_syntax"          # 解析失败（如 unclosed quote）
    # 解析成功但无法执行
    CMD_NOT_FOUND = "cmd_not_found"            # 未知命令
    PERMISSION_DENIED = "permission_denied"    # 权限不足
    CONFIRM_REQUIRED = "confirm_required"      # 敏感操作需确认
    LOCK_TIMEOUT = "lock_timeout"              # 分布式锁获取失败
    # 执行阶段
    NOT_IMPLEMENTED = "not_implemented"        # handler 未实现（V.1 stub 专用）
    INVALID_ARGS = "invalid_args"              # 参数校验失败
    INTERNAL_ERROR = "internal_error"          # handler 抛异常
    # 元结果
    PASSTHROUGH = "passthrough"                # 非命令，原样转发 LLM
    SUCCESS = "success"                        # 显式 success（与 result.success=True 对齐）


# ── 解析结果 ──────────────────────────────────────────────


@dataclass(slots=True)
class ParsedCommand:
    """解析后的命令中间表示."""

    name: str                                 # 命令名（不含 /），已展开 alias
    raw_name: str                             # 原始输入的命令名（保留 /r 形态）
    args: list[str] = field(default_factory=list)
    flags: dict[str, str | bool] = field(default_factory=dict)
    pipe_target: str | None = None            # 管道目标（v1 仅解析不执行）
    raw: str = ""                             # 原始输入（用于审计）

    @property
    def has_pipe(self) -> bool:
        return self.pipe_target is not None


# ── 执行上下文 ────────────────────────────────────────────


@dataclass(slots=True)
class CommandContext:
    """执行上下文 — executor 注入，handler 读取.

    permissions 是预解析好的权限级别列表，包含当前用户对 L1-L4 的可访问性，
    例如 ['L1_READONLY', 'L2_NORMAL']。
    """

    session_id: str
    user_id: str
    permissions: list[str] = field(default_factory=list)
    user_role: str | None = None
    db: Any | None = None                     # AsyncSession
    redis: Any | None = None                  # redis.asyncio.Redis
    extra: dict[str, Any] = field(default_factory=dict)


# ── 执行结果 ──────────────────────────────────────────────


@dataclass
class CommandResult:
    """执行结果.

    action 字段是"控制流信号"：
    - 'continue': 正常返回，message 给用户看
    - 'confirm_required': 前端弹确认窗
    - 'passthrough': 非命令（'//' 开头或未匹配），由调用方转发 LLM
    """

    success: bool
    message: str = ""
    data: Any = None
    error_code: CommandErrorCode = CommandErrorCode.SUCCESS
    action: str = "continue"
    snapshot_id: str | None = None
    confirmation_token: str | None = None
    duration_ms: float | None = None

    @property
    def code(self) -> str:
        """Backward-compat: 返回 error_code 的 value — 测试中常用 result.code."""
        return self.error_code.value

    @classmethod
    def success(
        cls,
        message: str,
        data: Any = None,
    ) -> "CommandResult":
        """成功结果 — 显式 success + SUCCESS error_code."""
        return cls(
            success=True,
            message=message,
            data=data,
            error_code=CommandErrorCode.SUCCESS,
        )

    @classmethod
    def passthrough(cls) -> "CommandResult":
        """非命令输入,应转发给 LLM."""
        return cls(
            success=False,
            action="passthrough",
            error_code=CommandErrorCode.PASSTHROUGH,
            message="非命令输入,已转发 LLM",
        )

    @classmethod
    def error(
        cls,
        code: CommandErrorCode,
        message: str = "",
        data: Any = None,
    ) -> "CommandResult":
        return cls(
            success=False,
            error_code=code,
            message=message,
            data=data,
        )

    @classmethod
    def confirm_required(
        cls,
        token: str,
        message: str = "敏感操作需确认",
        data: Any = None,
    ) -> "CommandResult":
        return cls(
            success=False,
            action="confirm_required",
            error_code=CommandErrorCode.CONFIRM_REQUIRED,
            confirmation_token=token,
            message=message,
            data=data,
        )


# ── Handler 协议 ─────────────────────────────────────────


@runtime_checkable
class CommandHandler(Protocol):
    """Handler 协议 — registry 通过此协议调用.

    registry.register() 接受的 dict 形式元数据:
        {
            "name": "/restart",
            "aliases": ["/r"],
            "category": CommandCategory.TASK,
            "description": "重启当前任务",
            "permissions": ["L2_NORMAL", "L3_SENSITIVE"],
            "need_confirm": True,
            "handler": async def(args, flags, context) -> CommandResult: ...
        }
    """

    name: str
    aliases: list[str]
    category: CommandCategory
    description: str
    permissions: list[str]
    need_confirm: bool
    handler: Callable[[list[str], dict[str, Any], CommandContext], Awaitable[CommandResult]]


HandlerCallable = Callable[[list[str], dict[str, Any], CommandContext], Awaitable[CommandResult]]
HandlerSpec = dict[str, Any]
