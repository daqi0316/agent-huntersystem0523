"""Task control command handlers — 任务控制 8 个命令 (V.2 真实实现).

生产模式:
  - /restart — 调用 orchestrator graph 创建新任务
  - /pause   — 降级: SnapshotManager 写 pause 标记 (Phase S.3 未就绪)
  - /resume  — 降级: SnapshotManager 写 resume 标记
  - /cancel  — ApprovalService 创建审批请求 (需 context.db)
  - /retry   — orchestrator graph 创建新 task
  - /rollback — SnapshotManager 预览快照
  - /snapshot — SnapshotManager 列出快照
  - /checkpoint — SnapshotManager 手动检查点

注册信息在文件末尾 TASK_CONTROL_COMMANDS.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.commands.types import (
    CommandCategory,
    CommandContext,
    CommandErrorCode,
    CommandResult,
)
from app.commands.permissions import Permission
from app.core.snapshot_manager import SnapshotManager

logger = logging.getLogger(__name__)

_snapshot_mgr: SnapshotManager | None = None
_orchestrator_graph: Any = None


def _get_snapshot_manager() -> SnapshotManager:
    global _snapshot_mgr
    if _snapshot_mgr is None:
        _snapshot_mgr = SnapshotManager()
    return _snapshot_mgr


def _get_orchestrator_graph() -> Any | None:
    """懒加载编排图 — 失败时返回 None (降级)."""
    global _orchestrator_graph
    if _orchestrator_graph is not None:
        return _orchestrator_graph
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from app.graphs.orchestrator_graph import create_orchestrator_graph

        _orchestrator_graph = create_orchestrator_graph(checkpointer=MemorySaver())
        return _orchestrator_graph
    except Exception as e:
        logger.warning("编排图加载失败 (降级): %s", e)
        return None


# ── 辅助 ──────────────────────────────────────────────────

def _data(handler: str, **kw: Any) -> dict[str, Any]:
    return {"handler": handler, **kw}


def _session_id(args: list[str], context: CommandContext) -> str | None:
    return args[0] if args else context.session_id


# ══════════════════════════════════════════════════════════════
# Handlers
# ══════════════════════════════════════════════════════════════


async def handle_restart(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """重新开始 — 优先编排图 (含原始输入), 降级 ConversationService."""
    input_text = ""
    if context.db and context.session_id:
        try:
            from app.services.conversation_service import ConversationService
            svc = ConversationService(context.db)
            msgs = await svc.get_last_n_messages(context.session_id, 1)
            if msgs:
                input_text = msgs[-1].content[:200]
        except Exception:
            pass

    graph = _get_orchestrator_graph()

    if graph is not None:
        task_id = str(uuid.uuid4())
        try:
            result = await graph.ainvoke(
                {
                    "task_id": task_id,
                    "user_id": context.user_id,
                    "job_id": "",
                    "intent": "",
                    "input_text": input_text or " ".join(args) or "重启任务",
                    "agent_result": None,
                    "error": None,
                    "status": "",
                    "multi_stage": False,
                    "sub_tasks": [],
                    "current_level": 0,
                    "levels": [],
                    "paused_at_level": None,
                    "results": [],
                    "shared_context": {},
                },
                config={"configurable": {"thread_id": task_id}},
            )
            return CommandResult.success(
                f"已重新开始任务 {task_id[:8]}...",
                data=_data("restart", task_id=task_id, intent=result.get("intent"), status=result.get("status")),
            )
        except Exception as e:
            logger.exception("编排图重启失败, 降级 ConversationService")

    if context.db:
        try:
            from app.services.conversation_service import ConversationService

            svc = ConversationService(context.db)
            title = " ".join(args) if args else "重新开始"
            session = await svc.create_session(context.user_id, title=title)
            return CommandResult.success(
                f"已创建新会话 {session.id[:8]}... (降级)",
                data=_data("restart", session_id=session.id, degraded=True),
            )
        except Exception as e:
            return CommandResult.error(
                CommandErrorCode.INTERNAL_ERROR,
                message=f"重启失败: {e}",
            )

    return CommandResult.error(
        CommandErrorCode.NOT_IMPLEMENTED,
        message="/restart 不可用: 编排图 + 数据库均未就绪",
    )


async def handle_pause(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """暂停 — 降级: SnapshotManager 写 pause 标记.

    真 pause 需 Phase S.3 (LangGraph interrupt + byte-equal).
    降级: 保存状态快照 + 标记 paused.
    """
    sid = _session_id(args, context)
    if not sid:
        return CommandResult.error(CommandErrorCode.INVALID_ARGS, message="用法: /pause <session_id>")

    snap = _get_snapshot_manager()
    snap_id = snap.create(
        state={"status": "paused", "paused_at": datetime.now(timezone.utc).isoformat()},
        task_id=sid,
        agent_type="system",
        step_name="pause",
        description="用户暂停 (V.2 降级, 依赖 Phase S.3)",
    )

    data = _data("pause", session_id=sid, snapshot_id=snap_id)
    if context.db:
        try:
            from app.services.conversation_service import ConversationService

            svc = ConversationService(context.db)
            updated = await svc.update_session_metadata(sid, {"status": "paused"})
            if updated:
                data["conversation_updated"] = True
        except Exception:
            pass

    return CommandResult.success(
        f"已暂停 {sid[:8]}... (降级)",
        data=data,
    )


async def handle_resume(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """恢复 — 降级: SnapshotManager 写 resume 标记.

    尝试恢复最近快照, 标记会话为 active.
    """
    sid = _session_id(args, context)
    if not sid:
        return CommandResult.error(CommandErrorCode.INVALID_ARGS, message="用法: /resume <session_id>")

    snap = _get_snapshot_manager()
    latest = snap.get_latest(sid)

    snap_id = snap.create(
        state={"status": "active", "resumed_at": datetime.now(timezone.utc).isoformat()},
        task_id=sid,
        agent_type="system",
        step_name="resume",
        description="用户恢复 (V.2 降级)",
    )

    data = _data("resume", session_id=sid, snapshot_id=snap_id, restored_from=latest)
    if context.db:
        try:
            from app.services.conversation_service import ConversationService

            svc = ConversationService(context.db)
            await svc.update_session_metadata(sid, {"status": "active"})
        except Exception:
            pass

    return CommandResult.success(
        f"已恢复 {sid[:8]}... (降级)",
        data=data,
    )


async def handle_cancel(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """取消任务 — 优先走 ApprovalService.

    确认流由 executor need_confirm 处理; 此处执行实际取消操作.
    """
    sid = _session_id(args, context)
    if not sid:
        return CommandResult.error(CommandErrorCode.INVALID_ARGS, message="用法: /cancel <session_id>")

    if context.db:
        try:
            from app.services.approval_service import ApprovalService

            svc = ApprovalService(context.db)
            approval = await svc.create(
                user_id=context.user_id,
                action_type="cancel_task",
                proposal={"session_id": sid, "reason": "用户取消"},
                target_type="session",
                target_id=sid,
            )
            snap = _get_snapshot_manager()
            snap.create(
                state={"status": "cancelled", "approval_id": approval.id},
                task_id=sid,
                agent_type="system",
                step_name="cancel",
                description=f"用户取消 (ApprovalService: {approval.id[:8]}...)",
            )
            return CommandResult.success(
                f"已提交取消请求 ({approval.id[:8]}...)",
                data=_data("cancel", session_id=sid, approval_id=approval.id),
            )
        except Exception as e:
            logger.warning("ApprovalService 降级: %s", e)

    snap = _get_snapshot_manager()
    snap.create(
        state={"status": "cancelled"},
        task_id=sid,
        agent_type="system",
        step_name="cancel",
        description="用户取消 (无 ApprovalService)",
    )
    return CommandResult.success(
        f"已取消 {sid[:8]}... (降级: 无审批流)",
        data=_data("cancel", session_id=sid),
    )


async def handle_retry(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """重试 — 通过 orchestrator graph 创建新任务.

    保留原任务的输入文本.
    """
    graph = _get_orchestrator_graph()
    if not graph:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/retry 不可用: 编排图未就绪",
        )

    sid = _session_id(args, context) or str(uuid.uuid4())
    new_task_id = str(uuid.uuid4())

    input_text = ""
    if context.db and sid:
        try:
            from app.services.conversation_service import ConversationService

            svc = ConversationService(context.db)
            msgs = await svc.get_last_n_messages(sid, 1)
            if msgs:
                input_text = msgs[-1].content[:200]
        except Exception:
            pass

    try:
        result = await graph.ainvoke(
            {
                "task_id": new_task_id,
                "user_id": context.user_id,
                "job_id": "",
                "intent": "",
                "input_text": input_text or "重试任务",
                "agent_result": None,
                "error": None,
                "status": "",
                "multi_stage": False,
                "sub_tasks": [],
                "current_level": 0,
                "levels": [],
                "paused_at_level": None,
                "results": [],
                "shared_context": {},
            },
            config={"configurable": {"thread_id": new_task_id}},
        )
    except Exception as e:
        logger.exception("重试任务失败")
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"重试失败: {e}",
        )

    return CommandResult.success(
        f"已创建重试任务 {new_task_id[:8]}...",
        data=_data("retry", task_id=result.get("task_id"), source_session=sid),
    )


async def handle_rollback(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """回滚 — 预览可恢复快照.

    用法: /rollback <task_id> [N]
    N 为回滚步数 (默认 1). 确认流由 executor need_confirm 处理.
    返回前 N 个快照预览, 用户确认后执行.
    """
    sid = _session_id(args, context)
    if not sid:
        return CommandResult.error(CommandErrorCode.INVALID_ARGS, message="用法: /rollback <task_id> [N]")

    try:
        steps = int(args[1]) if len(args) > 1 else 1
    except (ValueError, IndexError):
        steps = 1

    snap = _get_snapshot_manager()
    all_snapshots = snap.list_by_task(sid)
    preview = all_snapshots[:steps] if steps > 0 else all_snapshots

    return CommandResult.success(
        f"找到 {len(all_snapshots)} 个快照, 预览前 {len(preview)} 个",
        data=_data("rollback", task_id=sid, total=len(all_snapshots), preview_snapshots=preview),
    )


async def handle_snapshot(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """列出快照 — 从 SnapshotManager 查询."""
    sid = _session_id(args, context)
    if not sid:
        return CommandResult.error(CommandErrorCode.INVALID_ARGS, message="用法: /snapshot <task_id>")

    snap = _get_snapshot_manager()
    snapshots = snap.list_by_task(sid)

    return CommandResult.success(
        f"找到 {len(snapshots)} 个快照",
        data=_data("snapshot", task_id=sid, snapshots=snapshots),
    )


async def handle_checkpoint(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """手动检查点 — SnapshotManager 保存状态快照.

    用法: /checkpoint <task_id> [--description ...]
    """
    sid = _session_id(args, context)
    if not sid:
        return CommandResult.error(CommandErrorCode.INVALID_ARGS, message="用法: /checkpoint <task_id> [--description ...]")

    description = flags.get("description", flags.get("desc", "用户手动检查点"))
    snap = _get_snapshot_manager()
    snap_id = snap.create(
        state={"status": "checkpoint", "checkpoint_at": datetime.now(timezone.utc).isoformat()},
        task_id=sid,
        agent_type="system",
        step_name="checkpoint",
        description=str(description),
        is_auto=False,
    )
    return CommandResult.success(
        f"已创建检查点 {snap_id[:16]}...",
        data=_data("checkpoint", task_id=sid, snapshot_id=snap_id),
    )


# ══════════════════════════════════════════════════════════════
# 注册信息
# ══════════════════════════════════════════════════════════════

TASK_CONTROL_COMMANDS: list[dict] = [
    {
        "name": "/restart",
        "handler": handle_restart,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.TASK,
        "need_confirm": True,
        "aliases": ["/r"],
    },
    {
        "name": "/pause",
        "handler": handle_pause,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.TASK,
        "need_confirm": True,
        "aliases": ["/p"],
    },
    {
        "name": "/resume",
        "handler": handle_resume,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.TASK,
        "need_confirm": True,
        "aliases": [],
    },
    {
        "name": "/cancel",
        "handler": handle_cancel,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.TASK,
        "need_confirm": True,
        "aliases": [],
    },
    {
        "name": "/retry",
        "handler": handle_retry,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.TASK,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/rollback",
        "handler": handle_rollback,
        "permission": Permission.L3_ELEVATED,
        "category": CommandCategory.TASK,
        "need_confirm": True,
        "aliases": [],
    },
    {
        "name": "/snapshot",
        "handler": handle_snapshot,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.TASK,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/checkpoint",
        "handler": handle_checkpoint,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.TASK,
        "need_confirm": False,
        "aliases": [],
    },
]
