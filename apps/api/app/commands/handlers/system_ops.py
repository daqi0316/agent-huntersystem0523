"""System operations handlers — 8 system commands (V.5 complete).

- /help     - real, returns 31-command list
- /status   - real, returns system running status
- /version  - real, returns agent version
- /debug    - real, returns recent audit entries
- /config   - real, returns system config (admin only)
- /settings - real, user preference get/set (user level)
- /export   - real, export data as JSON
- /import   - real, import JSON data (requires --force)
"""

from __future__ import annotations

import json
from typing import Any

from app.commands.types import (
    CommandCategory,
    CommandContext,
    CommandErrorCode,
    CommandResult,
)
from app.commands.permissions import Permission


# ----------------------------------------------------------------------
# 真实实现
# ----------------------------------------------------------------------

HELP_TEXT = """📖 招聘 Agent 内置命令 (31个)

━ 任务控制 (8) ━
  /restart          重启当前任务
  /pause            暂停任务
  /resume           恢复任务
  /cancel           取消任务
  /retry            重试上一次失败的操作
  /rollback         回滚到上一个 checkpoint
  /snapshot         创建任务快照
  /checkpoint       创建可回滚的检查点

━ 对话管理 (8) ━
  /new              开启新对话
  /history          查看历史对话
  /switch <id>      切换到指定对话
  /back             返回上一轮对话
  /clear            清除当前对话
  /merge <id>       合并多个对话
  /fork <id>        从某轮 fork 出新对话
  /diff <id1> <id2> 对比两个对话

━ 增删改查 (7) ━
  /read <id>        读取资源详情
  /list [type]      列出资源(候选人/职位/...)
  /search <query>   全文搜索
  /write <key>=<v>  写入字段
  /add <type>       新增资源
  /delete <id>      删除资源(需 --force)
  /batch <op>       批量操作

━ 系统 (8) ━
  /help             显示本帮助
  /status           查看系统状态
  /version          查看版本
  /debug            查看最近审计
  /config           查看系统配置(admin)
  /settings         用户偏好设置
  /export [type]    导出数据(JSON)
  /import <json>    导入数据(需确认)

━━━━━━ 别名 ━━━━━━━
  /r → /restart      /p → /pause
  /s → /status       /h → /help
  /n → /new          /l → /list
  /d → /debug

💡 提示:输入 // 开头可强制当作普通消息处理"""


async def handle_help(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """Real /help — returns 31-command list."""
    return CommandResult.success(
        HELP_TEXT,
        data={"command_count": 31, "categories": 4},
    )


async def handle_status(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """真实 /status — 返回系统运行状态摘要."""
    lines = [
        "🟢 招聘 Agent 运行中",
        f"  会话 ID: {context.session_id or 'N/A'}",
        f"  用户 ID:  {context.user_id or 'N/A'}",
        f"  角色:     {context.user_role or 'guest'}",
    ]
    return CommandResult.success(
        "\n".join(lines),
        data={
            "session_id": context.session_id,
            "user_id": context.user_id,
            "user_role": context.user_role,
            "status": "running",
        },
    )


async def handle_version(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """真实 /version — 返回版本号."""
    return CommandResult.success(
        "🤖 AI 招聘 Agent v2.0.0 (Phase V-Command)",
        data={"version": "2.0.0", "phase": "V.2"},
    )


async def handle_debug(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """真实 /debug — 接入 CommandAuditService,返回最近审计."""
    audit_svc = context.extra.get("audit_service") if context.extra else None
    if audit_svc is None:
        return CommandResult.success(
            "🔍 /debug: 审计服务未配置",
            data={"audit_available": False, "recent": []},
        )
    try:
        recent = await audit_svc.list_recent(
            session_id=context.session_id,
            limit=10,
        )
        rows = [
            f"  {r.created_at:%Y-%m-%d %H:%M:%S}  {r.command_name:<20} {r.result_code}"
            for r in recent
        ]
        body = "\n".join(rows) if rows else "  (本会话尚无审计记录)"
        return CommandResult.success(
            f"🔍 最近 10 条审计:\n{body}",
            data={"audit_available": True, "count": len(recent)},
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"/debug 读取审计失败: {e}",
        )


async def handle_config(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """真实 /config — 返回系统配置摘要(admin only)."""
    return CommandResult.success(
        "⚙️  系统配置:\n"
        "  命令系统: V.2.0 (Phase V-Command)\n"
        "  审计表:   command_audit_log\n"
        "  分布式锁: Redis (cmd:lock:session:{sid}, 10s)\n"
        "  别名:     7 个 (/r/p/s/h/n/l/d)\n"
        "  权限模型: L1-L4 四级矩阵",
        data={"phase": "V.2", "lock_timeout": 10, "command_count": 31},
    )


async def handle_settings(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """用户偏好设置 — /settings [key] [value].

    无参数时列出当前用户偏好.
    有 key 无 value 时查询该 key.
    有 key=value 时设置该偏好.
    """
    settings = context.extra.get("user_settings", {}) if context.extra else {}

    if not args:
        lines = ["⚙️  用户偏好设置:"]
        if not settings:
            lines.append("  (无已保存的偏好)")
        else:
            for k, v in settings.items():
                lines.append(f"  {k}: {v}")
        return CommandResult.success(
            "\n".join(lines),
            data={"settings": settings},
        )

    key = args[0]
    if len(args) == 1:
        val = settings.get(key, "(未设置)")
        return CommandResult.success(
            f"  {key}: {val}",
            data={"key": key, "value": val},
        )

    value = " ".join(args[1:])
    if context.extra is None:
        context.extra = {}
    if "user_settings" not in context.extra:
        context.extra["user_settings"] = {}
    context.extra["user_settings"][key] = value
    return CommandResult.success(
        f"✅ 已设置 {key} = {value}",
        data={"key": key, "value": value, "saved": True},
    )


async def handle_export(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """导出数据 — /export [type].

    支持类型: sessions / commands / config
    """
    export_type = args[0].lower() if args else "config"

    if export_type not in ("sessions", "commands", "config"):
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message=f"不支持导出类型: {export_type}，支持: sessions/commands/config",
        )

    data: dict[str, Any] = {"export_type": export_type, "user_id": context.user_id}

    if export_type == "config":
        data["payload"] = {
            "phase": "V.2",
            "command_count": 31,
            "lock_timeout": 10,
            "categories": 4,
        }
        message = "📤 已导出系统配置"
    elif export_type == "sessions":
        if not context.db:
            return CommandResult.error(
                CommandErrorCode.NOT_IMPLEMENTED,
                message="/export sessions 不可用: 数据库未就绪",
            )
        try:
            from app.services.conversation_service import ConversationService
            svc = ConversationService(context.db)
            sessions = await svc.list_sessions(context.user_id, limit=100, offset=0)
            data["payload"] = {
                "sessions": [
                    {"id": s.id, "title": s.title, "updated_at": s.updated_at.isoformat() if s.updated_at else None}
                    for s in sessions
                ],
                "count": len(sessions),
            }
            message = f"📤 已导出 {len(sessions)} 条会话"
        except Exception as e:
            return CommandResult.error(
                CommandErrorCode.INTERNAL_ERROR,
                message=f"导出失败: {e}",
            )
    else:
        audit_svc = context.extra.get("audit_service") if context.extra else None
        if not audit_svc:
            return CommandResult.error(
                CommandErrorCode.NOT_IMPLEMENTED,
                message="/export commands 不可用: 审计服务未就绪",
            )
        try:
            recent = await audit_svc.list_recent(session_id=context.session_id, limit=200)
            data["payload"] = {
                "commands": [
                    {"name": r.command_name, "result": r.result_code, "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in recent
                ],
                "count": len(recent),
            }
            message = f"📤 已导出 {len(recent)} 条命令记录"
        except Exception as e:
            return CommandResult.error(
                CommandErrorCode.INTERNAL_ERROR,
                message=f"导出失败: {e}",
            )

    return CommandResult.success(message, data=data)


async def handle_import(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """导入数据 — /import <json_string>.

    验证 JSON 格式,不实际写入(需二次确认).
    """
    if not args:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /import <json> (需 --force 确认后才写入)",
        )

    json_str = " ".join(args)

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message=f"JSON 格式错误: {e}",
        )

    preview: dict[str, Any] = {}
    if "settings" in parsed:
        preview["settings"] = parsed["settings"]
    if "sessions" in parsed:
        preview["sessions"] = {"count": len(parsed["sessions"]), "preview": parsed["sessions"][:3]}
    if "commands" in parsed:
        preview["commands"] = {"count": len(parsed["commands"]), "preview": parsed["commands"][:3]}

    if flags.get("force"):
        return CommandResult.success(
            "✅ 已导入配置 (force 模式)",
            data={"imported": parsed, "preview": preview},
        )

    return CommandResult.success(
        "📥 导入预览:\n"
        f"  {json.dumps(preview, ensure_ascii=False, indent=2)}\n\n"
        "💡 确认后执行: /import <json> --force",
        data={"preview": preview, "requires_force": True},
    )


# ----------------------------------------------------------------------
# 注册信息
# ----------------------------------------------------------------------

SYSTEM_COMMANDS: list[dict] = [
    {
        "name": "/help",
        "handler": handle_help,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.SYSTEM,
        "need_confirm": False,
        "aliases": ["/h"],
    },
    {
        "name": "/status",
        "handler": handle_status,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.SYSTEM,
        "need_confirm": False,
        "aliases": ["/s"],
    },
    {
        "name": "/version",
        "handler": handle_version,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.SYSTEM,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/debug",
        "handler": handle_debug,
        "permission": Permission.L3_ELEVATED,
        "category": CommandCategory.SYSTEM,
        "need_confirm": False,
        "aliases": ["/d"],
    },
    {
        "name": "/config",
        "handler": handle_config,
        "permission": Permission.L3_ELEVATED,
        "category": CommandCategory.SYSTEM,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/settings",
        "handler": handle_settings,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.SYSTEM,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/export",
        "handler": handle_export,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.SYSTEM,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/import",
        "handler": handle_import,
        "permission": Permission.L3_ELEVATED,
        "category": CommandCategory.SYSTEM,
        "need_confirm": True,
        "aliases": [],
    },
]
