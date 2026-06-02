"""Dialog command handlers — 对话管理 8 个命令 (V.3 真实实现).

实现逻辑:
- /new        — 创建新 ConversationSession
- /history    — 列出当前用户的会话列表
- /switch     — 切换当前活跃会话 (Redis)
- /back       — 返回上一会话
- /clear      — 清空当前会话消息
- /fork       — 复制会话 (复制消息)
- /merge      — 合并两个会话消息
- /diff       — 对比两个会话差异

注册信息在文件末尾 DIALOG_COMMANDS.
"""

from __future__ import annotations

import logging
from typing import Any

from app.commands.types import (
    CommandCategory,
    CommandContext,
    CommandErrorCode,
    CommandResult,
)
from app.commands.permissions import Permission
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

_CURRENT_KEY = "conversation:current:{user_id}"
_PREVIOUS_KEY = "conversation:previous:{user_id}"


def _redis_key(template: str, user_id: str) -> str:
    return template.format_map({"user_id": user_id})


def _data(handler: str, **kw: Any) -> dict[str, Any]:
    return {"handler": handler, **kw}


async def handle_new(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """创建新会话 — ConversationService.create_session + 设为当前."""
    title = " ".join(args) if args else "新对话"
    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/new 不可用: 数据库未就绪",
        )

    try:
        svc = ConversationService(context.db)
        session = await svc.create_session(context.user_id, title=title)

        if context.redis:
            try:
                prev = await context.redis.get(_redis_key(_CURRENT_KEY, context.user_id))
                if prev:
                    await context.redis.set(_redis_key(_PREVIOUS_KEY, context.user_id), prev)
                await context.redis.set(_redis_key(_CURRENT_KEY, context.user_id), session.id)
            except Exception as e:
                logger.warning("Redis session tracking failed: %s", e)

        return CommandResult.success(
            f"✅ 新会话已创建：{session.title or '新对话'}",
            data=_data("new", session_id=session.id, title=session.title),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"创建会话失败: {e}",
        )


async def handle_history(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """列出用户的所有会话 — ConversationService.list_sessions."""
    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/history 不可用: 数据库未就绪",
        )

    try:
        limit = 20
        offset = 0
        if args:
            try:
                limit = min(int(args[0]), 100)
            except ValueError:
                pass

        svc = ConversationService(context.db)
        sessions = await svc.list_sessions(context.user_id, limit=limit, offset=offset)

        items = [
            {
                "session_id": s.id,
                "title": s.title,
                "updated_at": s.updated_at.isoformat() if s.updated_at else "",
                "message_count": await svc.get_session_message_count(s.id),
            }
            for s in sessions
        ]
        return CommandResult.success(
            f"找到 {len(items)} 个会话",
            data=_data("history", sessions=items),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"获取会话列表失败: {e}",
        )


async def handle_switch(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """切换活跃会话 — Redis 存储 + 更新 metadata."""
    if not args:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /switch <session_id>",
        )

    target_id = args[0]
    current_id = context.session_id

    if current_id and context.redis:
        try:
            await context.redis.set(_redis_key(_PREVIOUS_KEY, context.user_id), current_id)
        except Exception as e:
            logger.warning("Redis save previous failed: %s", e)

    if context.redis:
        try:
            await context.redis.set(_redis_key(_CURRENT_KEY, context.user_id), target_id)
        except Exception as e:
            logger.warning("Redis session switch failed: %s", e)

    if context.db:
        try:
            svc = ConversationService(context.db)
            await svc.update_session_metadata(target_id, {"switched_at": __import__("datetime").datetime.now().isoformat()})
        except Exception:
            pass

    return CommandResult.success(
        f"已切换到会话 {target_id[:8]}...",
        data=_data("switch", session_id=target_id, previous_id=current_id),
    )


async def handle_back(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """返回上一会话 — 从 Redis 读取并切换."""
    if not context.redis:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/back 不可用: Redis 未就绪",
        )

    try:
        prev_id = await context.redis.get(_redis_key(_PREVIOUS_KEY, context.user_id))
        if not prev_id:
            return CommandResult.error(
                CommandErrorCode.INVALID_ARGS,
                message="没有上一个会话",
            )

        current_id = await context.redis.get(_redis_key(_CURRENT_KEY, context.user_id))
        if current_id:
            await context.redis.set(_redis_key(_PREVIOUS_KEY, context.user_id), current_id)
        await context.redis.set(_redis_key(_CURRENT_KEY, context.user_id), prev_id)

        return CommandResult.success(
            f"已返回上一会话 {prev_id[:8]}...",
            data=_data("back", session_id=prev_id),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"切换失败: {e}",
        )


async def handle_clear(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """清空会话消息 — ConversationService delete + 确认."""
    sid = args[0] if args else context.session_id
    if not sid:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /clear [session_id]",
        )

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/clear 不可用: 数据库未就绪",
        )

    try:
        svc = ConversationService(context.db)
        count = await svc.get_session_message_count(sid)
        deleted = await svc.delete_session(sid)
        return CommandResult.success(
            f"已清空会话 {sid[:8]}... ({count} 条消息)",
            data=_data("clear", session_id=sid, deleted=deleted, message_count=count),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"清空失败: {e}",
        )


async def handle_fork(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """复制会话 — 创建新 session + 复制所有消息."""
    if not args:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /fork <source_session_id>",
        )

    source_id = args[0]
    title = " ".join(args[1:]) if len(args) > 1 else "会话副本"

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/fork 不可用: 数据库未就绪",
        )

    try:
        svc = ConversationService(context.db)
        source = await svc.get_session(source_id)
        if not source:
            return CommandResult.error(
                CommandErrorCode.INVALID_ARGS,
                message=f"源会话不存在: {source_id[:8]}...",
            )

        new_session = await svc.create_session(context.user_id, title=title)

        source_msgs = await svc.get_history(source_id, limit=1000)
        if source_msgs:
            msgs_to_copy = [
                {
                    "session_id": new_session.id,
                    "user_id": context.user_id,
                    "role": m.role,
                    "content": m.content,
                    "tool_calls": m.tool_calls,
                    "tool_result": m.tool_result,
                }
                for m in source_msgs
            ]
            await svc.add_messages(msgs_to_copy)

        return CommandResult.success(
            f"已复制会话 {source_id[:8]}... → {new_session.id[:8]}...",
            data=_data("fork", new_session_id=new_session.id, source_id=source_id, message_count=len(source_msgs)),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"复制失败: {e}",
        )


async def handle_merge(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """合并两个会话 — 从 source 复制消息到 target."""
    if len(args) < 2:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /merge <source_id> <target_id>",
        )

    source_id = args[0]
    target_id = args[1]

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/merge 不可用: 数据库未就绪",
        )

    try:
        svc = ConversationService(context.db)
        source = await svc.get_session(source_id)
        target = await svc.get_session(target_id)
        if not source:
            return CommandResult.error(
                CommandErrorCode.INVALID_ARGS,
                message=f"源会话不存在: {source_id[:8]}...",
            )
        if not target:
            return CommandResult.error(
                CommandErrorCode.INVALID_ARGS,
                message=f"目标会话不存在: {target_id[:8]}...",
            )

        source_msgs = await svc.get_history(source_id, limit=1000)
        if not source_msgs:
            return CommandResult.success(
                f"源会话无消息",
                data=_data("merge", source_id=source_id, target_id=target_id, count=0),
            )

        msgs_to_merge = [
            {
                "session_id": target_id,
                "user_id": context.user_id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "tool_result": m.tool_result,
            }
            for m in source_msgs
        ]
        await svc.add_messages(msgs_to_merge)

        return CommandResult.success(
            f"已合并 {len(source_msgs)} 条消息: {source_id[:8]}... → {target_id[:8]}...",
            data=_data("merge", source_id=source_id, target_id=target_id, count=len(source_msgs)),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"合并失败: {e}",
        )


async def handle_diff(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """对比两个会话 — 消息内容级别 diff."""
    if len(args) < 2:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /diff <session_a> <session_b>",
        )

    a_id = args[0]
    b_id = args[1]

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/diff 不可用: 数据库未就绪",
        )

    try:
        svc = ConversationService(context.db)
        msgs_a = await svc.get_history(a_id, limit=500)
        msgs_b = await svc.get_history(b_id, limit=500)

        content_a = [m.content for m in msgs_a]
        content_b = [m.content for m in msgs_b]

        only_a = [c for c in content_a if c not in content_b]
        only_b = [c for c in content_b if c not in content_a]

        return CommandResult.success(
            f"会话差异: A 独有 {len(only_a)} 条, B 独有 {len(only_b)} 条",
            data=_data("diff", session_a=a_id, session_b=b_id,
                       a_count=len(msgs_a), b_count=len(msgs_b),
                       only_in_a=only_a[:10], only_in_b=only_b[:10]),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"对比失败: {e}",
        )


# ============================================================================
# 注册信息
# ============================================================================

DIALOG_COMMANDS: list[dict] = [
    {
        "name": "/new",
        "handler": handle_new,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.DIALOG,
        "need_confirm": False,
        "aliases": ["/n"],
    },
    {
        "name": "/history",
        "handler": handle_history,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.DIALOG,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/switch",
        "handler": handle_switch,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.DIALOG,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/back",
        "handler": handle_back,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.DIALOG,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/clear",
        "handler": handle_clear,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.DIALOG,
        "need_confirm": True,
        "aliases": [],
    },
    {
        "name": "/fork",
        "handler": handle_fork,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.DIALOG,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/merge",
        "handler": handle_merge,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.DIALOG,
        "need_confirm": True,
        "aliases": [],
    },
    {
        "name": "/diff",
        "handler": handle_diff,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.DIALOG,
        "need_confirm": False,
        "aliases": [],
    },
]