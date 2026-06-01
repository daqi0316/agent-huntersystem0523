"""CRUD command handlers — 增删改查 7 个命令 (V.4 真实实现).

支持的实体类型:
- candidate   / jd     (JobPosition)
- application / app   (Application)

用法示例:
- /read candidate <id>
- /list candidates [--limit 20] [--offset 0]
- /search candidates "关键词"
- /add candidate name="张三" email="zhangsan@example.com" skills="Python,Go"
- /write candidate <id> status=archived
- /delete candidate <id>
- /batch delete candidates <id1> <id2> ...
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, delete, func

from app.commands.types import (
    CommandCategory,
    CommandContext,
    CommandErrorCode,
    CommandResult,
)
from app.commands.permissions import Permission
from app.models.candidate import Candidate, CandidateStatus
from app.models.job_position import JobPosition, JobStatus
from app.models.application import Application, ApplicationStatus

logger = logging.getLogger(__name__)

_ENTITY_MODELS: dict[str, type] = {
    "candidate": Candidate,
    "candidates": Candidate,
    "jd": JobPosition,
    "job": JobPosition,
    "jobs": JobPosition,
    "application": Application,
    "applications": Application,
}

_STATUS_ENUMS: dict[str, type] = {
    "candidate": CandidateStatus,
    "candidates": CandidateStatus,
    "jd": JobStatus,
    "job": JobStatus,
    "jobs": JobStatus,
    "application": ApplicationStatus,
    "applications": ApplicationStatus,
}


def _data(handler: str, **kw: Any) -> dict[str, Any]:
    return {"handler": handler, **kw}


def _parse_entity(args: list[str]) -> tuple[str, str | None]:
    """从 args 解析 entity_type 和 id/keyword。"""
    if not args:
        return "", None
    entity = args[0].lower()
    rest = args[1:]
    value = rest[0] if rest else None
    return entity, value


def _get_model(entity: str):
    return _ENTITY_MODELS.get(entity.lower())


# ══════════════════════════════════════════════════════════════
# /read
# ══════════════════════════════════════════════════════════════


async def handle_read(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """读取单个实体 — /read <entity> <id>"""
    if len(args) < 2:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /read <entity> <id>",
        )

    entity = args[0].lower()
    entity_id = args[1]

    model = _get_model(entity)
    if not model:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message=f"未知实体: {entity}，支持: candidate/jd/application",
        )

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/read 不可用: 数据库未就绪",
        )

    try:
        stmt = select(model).where(model.id == entity_id)
        result = await context.db.execute(stmt)
        row = result.scalar_one_or_none()

        if not row:
            return CommandResult.error(
                CommandErrorCode.INVALID_ARGS,
                message=f"{entity} {entity_id[:8]}... 不存在",
            )

        data = _row_to_dict(row)
        return CommandResult.success(
            f"已读取 {entity} {entity_id[:8]}...",
            data=_data("read", entity=entity, id=entity_id, data=data),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"读取失败: {e}",
        )


# ══════════════════════════════════════════════════════════════
# /list
# ══════════════════════════════════════════════════════════════


async def handle_list(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """列出实体列表 — /list <entity> [--limit N] [--offset N]"""
    if not args:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /list <entity> [--limit N] [--offset N]",
        )

    entity = args[0].lower()
    model = _get_model(entity)
    if not model:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message=f"未知实体: {entity}，支持: candidate/jd/application",
        )

    limit = 20
    offset = 0
    for i, arg in enumerate(args):
        if arg == "--limit" and i + 1 < len(args):
            try:
                limit = min(int(args[i + 1]), 100)
            except ValueError:
                pass
        if arg == "--offset" and i + 1 < len(args):
            try:
                offset = max(int(args[i + 1]), 0)
            except ValueError:
                pass

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/list 不可用: 数据库未就绪",
        )

    try:
        count_stmt = select(func.count()).select_from(model)
        count_result = await context.db.execute(count_stmt)
        total = count_result.scalar() or 0

        list_stmt = select(model).order_by(model.created_at.desc()).offset(offset).limit(limit)
        list_result = await context.db.execute(list_stmt)
        rows = list(list_result.scalars().all())

        items = [_row_to_dict(r) for r in rows]
        return CommandResult.success(
            f"找到 {len(items)} 个 {entity}（共 {total}）",
            data=_data("list", entity=entity, items=items, total=total, limit=limit, offset=offset),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"列表查询失败: {e}",
        )


# ══════════════════════════════════════════════════════════════
# /search
# ══════════════════════════════════════════════════════════════


async def handle_search(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """搜索实体 — /search <entity> <keyword>"""
    if len(args) < 2:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /search <entity> <keyword>",
        )

    entity = args[0].lower()
    keyword = args[1]

    model = _get_model(entity)
    if not model:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message=f"未知实体: {entity}",
        )

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/search 不可用: 数据库未就绪",
        )

    try:
        col = _search_column(model)
        if not col:
            return CommandResult.error(
                CommandErrorCode.INTERNAL_ERROR,
                message=f"{entity} 不支持按名称搜索",
            )

        stmt = select(model).where(col.ilike(f"%{keyword}%")).limit(50)
        result = await context.db.execute(stmt)
        rows = list(result.scalars().all())

        items = [_row_to_dict(r) for r in rows]
        return CommandResult.success(
            f"找到 {len(items)} 个匹配 {entity}",
            data=_data("search", entity=entity, keyword=keyword, items=items),
        )
    except Exception as e:
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"搜索失败: {e}",
        )


# ══════════════════════════════════════════════════════════════
# /add
# ══════════════════════════════════════════════════════════════


async def handle_add(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """创建新实体 — /add candidate name="张三" email="a@b.com" ..."""
    if len(args) < 2:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /add <entity> <field>=<value> ...",
        )

    entity = args[0].lower()
    model = _get_model(entity)
    if not model:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message=f"未知实体: {entity}",
        )

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/add 不可用: 数据库未就绪",
        )

    fields = _parse_kv_args(args[1:])
    if not fields:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="至少需要一个字段: name=value",
        )

    try:
        status_enum = _STATUS_ENUMS.get(entity)
        if status_enum and "status" in fields:
            try:
                fields["status"] = status_enum(fields["status"])
            except ValueError:
                return CommandResult.error(
                    CommandErrorCode.INVALID_ARGS,
                    message=f"无效状态: {fields['status']}",
                )

        obj = model(**fields)
        context.db.add(obj)
        await context.db.commit()
        await context.db.refresh(obj)

        return CommandResult.success(
            f"已创建 {entity} {obj.id[:8]}...",
            data=_data("add", entity=entity, id=obj.id, data=_row_to_dict(obj)),
        )
    except Exception as e:
        await context.db.rollback()
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"创建失败: {e}",
        )


# ══════════════════════════════════════════════════════════════
# /write
# ══════════════════════════════════════════════════════════════


async def handle_write(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """更新实体字段 — /write <entity> <id> <field>=<value> ..."""
    if len(args) < 3:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /write <entity> <id> <field>=<value> ...",
        )

    entity = args[0].lower()
    entity_id = args[1]

    model = _get_model(entity)
    if not model:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message=f"未知实体: {entity}",
        )

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/write 不可用: 数据库未就绪",
        )

    fields = _parse_kv_args(args[2:])
    if not fields:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="至少需要一个字段: name=value",
        )

    try:
        stmt = select(model).where(model.id == entity_id)
        result = await context.db.execute(stmt)
        obj = result.scalar_one_or_none()
        if not obj:
            return CommandResult.error(
                CommandErrorCode.INVALID_ARGS,
                message=f"{entity} {entity_id[:8]}... 不存在",
            )

        status_enum = _STATUS_ENUMS.get(entity)
        if status_enum and "status" in fields:
            try:
                fields["status"] = status_enum(fields["status"])
            except ValueError:
                return CommandResult.error(
                    CommandErrorCode.INVALID_ARGS,
                    message=f"无效状态: {fields['status']}",
                )

        for k, v in fields.items():
            setattr(obj, k, v)

        await context.db.commit()
        await context.db.refresh(obj)

        return CommandResult.success(
            f"已更新 {entity} {entity_id[:8]}...",
            data=_data("write", entity=entity, id=entity_id, data=_row_to_dict(obj)),
        )
    except Exception as e:
        await context.db.rollback()
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"更新失败: {e}",
        )


# ══════════════════════════════════════════════════════════════
# /delete
# ══════════════════════════════════════════════════════════════


async def handle_delete(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """删除实体 — /delete <entity> <id>"""
    if len(args) < 2:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /delete <entity> <id>",
        )

    entity = args[0].lower()
    entity_id = args[1]

    model = _get_model(entity)
    if not model:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message=f"未知实体: {entity}",
        )

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/delete 不可用: 数据库未就绪",
        )

    try:
        stmt = select(model).where(model.id == entity_id)
        result = await context.db.execute(stmt)
        obj = result.scalar_one_or_none()
        if not obj:
            return CommandResult.error(
                CommandErrorCode.INVALID_ARGS,
                message=f"{entity} {entity_id[:8]}... 不存在",
            )

        del_stmt = delete(model).where(model.id == entity_id)
        await context.db.execute(del_stmt)
        await context.db.commit()

        return CommandResult.success(
            f"已删除 {entity} {entity_id[:8]}...",
            data=_data("delete", entity=entity, id=entity_id),
        )
    except Exception as e:
        await context.db.rollback()
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"删除失败: {e}",
        )


# ══════════════════════════════════════════════════════════════
# /batch
# ══════════════════════════════════════════════════════════════


async def handle_batch(args: list[str], flags: dict, context: CommandContext) -> CommandResult:
    """批量操作 — /batch delete <entity> <id1> <id2> ..."""
    if len(args) < 3:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="用法: /batch delete <entity> <id1> [id2 ...]",
        )

    action = args[0].lower()
    entity = args[1].lower()
    ids = args[2:]

    if action not in ("delete", "close", "archive"):
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message="支持的操作: delete / close / archive",
        )

    model = _get_model(entity)
    if not model:
        return CommandResult.error(
            CommandErrorCode.INVALID_ARGS,
            message=f"未知实体: {entity}",
        )

    if not context.db:
        return CommandResult.error(
            CommandErrorCode.NOT_IMPLEMENTED,
            message="/batch 不可用: 数据库未就绪",
        )

    try:
        status_enum = _STATUS_ENUMS.get(entity)
        affected = 0

        if action == "delete":
            stmt = delete(model).where(model.id.in_(ids))
            result = await context.db.execute(stmt)
            await context.db.commit()
            affected = result.rowcount or 0

        elif action in ("close", "archive") and status_enum:
            target_status = _resolve_status(status_enum, action)

            if target_status is None:
                return CommandResult.error(
                    CommandErrorCode.INVALID_ARGS,
                    message=f"{entity} 不支持 {action} 操作",
                )

            for eid in ids:
                stmt = select(model).where(model.id == eid)
                result = await context.db.execute(stmt)
                obj = result.scalar_one_or_none()
                if obj:
                    obj.status = target_status
                    affected += 1
            await context.db.commit()

        return CommandResult.success(
            f"批量 {action} 完成: {affected} 条",
            data=_data("batch", action=action, entity=entity, affected=affected, ids=ids),
        )
    except Exception as e:
        await context.db.rollback()
        return CommandResult.error(
            CommandErrorCode.INTERNAL_ERROR,
            message=f"批量操作失败: {e}",
        )


# ══════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════


def _row_to_dict(row: Any) -> dict[str, Any]:
    """将 ORM 对象转 dict（处理 enum/value）。"""
    result: dict[str, Any] = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if hasattr(val, "value"):
            val = val.value
        result[col.name] = val
    return result


def _search_column(model: type) -> Any | None:
    """返回模型中用于 search 的字符串列。"""
    name_col = getattr(model, "name", None)
    if name_col is not None:
        return name_col
    title_col = getattr(model, "title", None)
    if title_col is not None:
        return title_col
    return None


def _parse_kv_args(args: list[str]) -> dict[str, Any]:
    """解析 name=value 形式的 args 为 dict。"""
    result: dict[str, Any] = {}
    for arg in args:
        if "=" in arg:
            key, val = arg.split("=", 1)
            key = key.strip()
            val = val.strip()
            if val.lower() == "null" or val == "":
                result[key] = None
            elif val.lower() in ("true", "false"):
                result[key] = val.lower() == "true"
            elif val.isdigit():
                result[key] = int(val)
            else:
                result[key] = val
    return result


def _resolve_status(enum_cls: type, action: str) -> Any | None:
    """将 action 字符串映射为枚举值（匹配 enum value 字符串）。"""
    mapping = {
        "archive": "archived",
        "close": "closed",
    }
    val = mapping.get(action)
    if val is None:
        return None
    try:
        return enum_cls(val)
    except ValueError:
        return None


# ══════════════════════════════════════════════════════════════
# 注册信息
# ══════════════════════════════════════════════════════════════

CRUD_COMMANDS: list[dict] = [
    {
        "name": "/read",
        "handler": handle_read,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.CRUD,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/list",
        "handler": handle_list,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.CRUD,
        "need_confirm": False,
        "aliases": ["/l"],
    },
    {
        "name": "/search",
        "handler": handle_search,
        "permission": Permission.L1_BASIC,
        "category": CommandCategory.CRUD,
        "need_confirm": False,
        "aliases": [],
    },
    {
        "name": "/write",
        "handler": handle_write,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.CRUD,
        "need_confirm": True,
        "aliases": [],
    },
    {
        "name": "/add",
        "handler": handle_add,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.CRUD,
        "need_confirm": True,
        "aliases": [],
    },
    {
        "name": "/delete",
        "handler": handle_delete,
        "permission": Permission.L2_CONFIRM,
        "category": CommandCategory.CRUD,
        "need_confirm": True,
        "aliases": [],
    },
    {
        "name": "/batch",
        "handler": handle_batch,
        "permission": Permission.L3_ELEVATED,
        "category": CommandCategory.CRUD,
        "need_confirm": True,
        "aliases": [],
    },
]