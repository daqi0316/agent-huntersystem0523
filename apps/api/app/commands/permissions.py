"""Permissions — 4 级权限矩阵 + @require_permission 装饰器.

与 plan §5.2 权限矩阵对齐:
    L1_BASIC    - 只读 / 状态查询 (所有角色可用)
    L2_CONFIRM  - 普通写操作 (editor 及以上)
    L3_ELEVATED - 高危操作,需 elevate (manager 及以上)
    L4_ADMIN    - 危险操作,仅管理员 (admin/owner)

handler 在注册时声明最低权限级别, executor 在调用前完成校验.
"""

from __future__ import annotations

import enum
from typing import Any, Awaitable, Callable

from app.commands.types import CommandContext, CommandResult


class Permission(enum.IntEnum):
    """4 级权限级别 (IntEnum 简化排序与比较)."""

    L1_BASIC = 1
    L2_CONFIRM = 2
    L3_ELEVATED = 3
    L4_ADMIN = 4


def has_permission(
    perm: Permission,
    permissions: list[str] | None,
) -> tuple[bool, str | None]:
    """检查用户的 permissions 列表是否满足 perm 级别.

    隐式授予: 拥有 L3_ELEVATED 即同时拥有 L1_BASIC + L2_CONFIRM (由 IntEnum
    排序实现 — 用户的最高级别 >= perm 即允许).

    Args:
        perm: handler 要求的最低权限级别
        permissions: 用户拥有的权限名列表, 例如 ['L1_BASIC', 'L3_ELEVATED']

    Returns:
        (allowed, reason) — allowed=True 时 reason=None
    """
    if not permissions:
        return False, "权限不足: 用户没有任何权限"
    user_max = 0
    for p in permissions:
        try:
            level = Permission[p]
        except KeyError:
            continue
        if int(level) > user_max:
            user_max = int(level)
    if user_max >= int(perm):
        return True, None
    return False, (
        f"权限不足: 需要 {perm.name} 级别 (当前最高: {_describe(permissions)})"
    )


def _describe(permissions: list[str]) -> str:
    if not permissions:
        return "无"
    levels: list[str] = []
    for p in permissions:
        try:
            levels.append(Permission[p].name)
        except KeyError:
            levels.append(p)
    return "/".join(levels) if levels else "无"


def require_permission(level: Permission) -> Callable:
    """装饰器: 标记 handler 需要的最低权限级别.

    此装饰器只标记元数据, 实际校验由 executor 在调用前完成.
    """

    def decorator(
        func: Callable[[list[str], dict[str, Any], CommandContext], Awaitable[CommandResult]],
    ) -> Callable:
        func.__permission_level__ = level  # type: ignore[attr-defined]
        return func

    return decorator


def check_permission(
    required: Permission | list[Permission],
    context: CommandContext,
) -> tuple[bool, str | None]:
    """executor 调用的权限校验入口.

    Args:
        required: 单个 Permission, 或 "OR" 关系的多 Permission 列表
        context: 执行上下文

    Returns:
        (allowed, reason) — allowed=True 时 reason=None
    """
    if isinstance(required, Permission):
        required = [required]
    if not required:
        return True, None
    for r in required:
        ok, _ = has_permission(r, context.permissions)
        if ok:
            return True, None
    return False, (
        f"权限不足: 此命令需要 {'/'.join(r.name for r in required)} 级别"
    )


def role_to_permissions(role: str | None) -> list[str]:
    """Map app user role to command system permission list.

    Defaults to L1_BASIC (read-only) for unknown roles.
    """
    if not role:
        return ["L1_BASIC"]
    mapping: dict[str, list[str]] = {
        "viewer": ["L1_BASIC"],
        "recruiter": ["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED"],
        "hiring_manager": ["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED"],
        "admin": ["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
        "owner": ["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
    }
    return mapping.get(role, ["L1_BASIC"])
