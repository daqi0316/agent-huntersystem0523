"""CommandRegistry — 28 个命令的注册中心.

设计要点：
- 注册时名字统一去掉前导 '/'
- 别名存储为小写（与 parser 输出一致）
- get(name) 支持通过别名查找
- register_all() 在模块加载时调用，导入并注册全部 28 个命令
- 重复注册同名/同别名抛 ValueError（防 typo）
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.commands.types import CommandCategory, CommandContext, CommandResult

logger = logging.getLogger(__name__)


# ── Registry 主体 ──────────────────────────────────────


class CommandRegistry:
    """命令注册中心 — 单例."""

    def __init__(self) -> None:
        # 主表: name -> spec
        self._commands: dict[str, dict[str, Any]] = {}
        # 别名表: alias -> name
        self._aliases: dict[str, str] = {}

    # ── 注册 ──────────────────────────────────────────

    def register(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """注册一个命令.

        接受两种形式:
        - reg.register(spec: dict)
        - reg.register(name=..., handler=..., category=..., ...)

        spec/kwargs 必须包含: name, category, handler
        可选: description, permission(s), aliases, need_confirm
        """
        # 解析参数形式
        if args and not kwargs:
            if len(args) > 1:
                raise TypeError("register 最多接受 1 个位置参数 (dict)")
            if not isinstance(args[0], dict):
                raise TypeError(
                    f"register 位置参数必须是 dict, 收到 {type(args[0]).__name__}"
                )
            spec = args[0]
        elif kwargs and not args:
            spec = kwargs
        else:
            raise TypeError("register 接受 dict 或 kwargs, 不能同时传两者")

        for required_key in ("name", "category", "handler"):
            if required_key not in spec:
                raise ValueError(f"spec 缺少必填字段: {required_key}")

        if not isinstance(spec["category"], CommandCategory):
            raise ValueError(
                f"category 必须是 CommandCategory, 收到 {type(spec['category']).__name__}"
            )

        handler: Callable = spec["handler"]
        if not callable(handler):
            raise TypeError(f"handler 必须是 callable, 收到 {type(handler).__name__}")

        name = self._normalize_name(spec["name"])
        if name in self._commands:
            raise ValueError(f"命令重复注册: {name!r}")

        normalized: dict[str, Any] = {
            **spec,
            "name": name,
            "description": spec.get("description", ""),
            "aliases": [self._normalize_name(a) for a in spec.get("aliases", [])],
            "permission": spec.get("permission", spec.get("permissions")),
            "need_confirm": bool(spec.get("need_confirm", False)),
        }
        # 移除多余的 'permissions' (plural) 字段
        normalized.pop("permissions", None)

        self._commands[name] = normalized
        for alias in normalized["aliases"]:
            if alias == name:
                # 防止 alias == name 干扰查找
                continue
            if alias in self._aliases and self._aliases[alias] != name:
                raise ValueError(
                    f"别名 {alias!r} 已注册到 {self._aliases[alias]!r}, 不能再注册到 {name!r}"
                )
            self._aliases[alias] = name
        logger.debug("命令已注册: /%s (aliases=%s)", name, normalized["aliases"])

    # ── 查询 ──────────────────────────────────────────

    def get(self, name: str) -> dict[str, Any] | None:
        """通过名字或别名查询命令 spec."""
        key = self._normalize_name(name)
        if key in self._commands:
            return self._commands[key]
        if key in self._aliases:
            return self._commands[self._aliases[key]]
        return None

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    _CATEGORY_ORDER: dict[CommandCategory, int] = {
        CommandCategory.TASK: 0,
        CommandCategory.DIALOG: 1,
        CommandCategory.CRUD: 2,
        CommandCategory.SYSTEM: 3,
    }

    def list_by_category(self, category: CommandCategory | str | None = None) -> list[dict[str, Any]]:
        """列出命令,可选按 category 过滤.

        返回 list[spec],按 (category_order, name) 排序保证稳定输出.
        category_order: TASK=0, DIALOG=1, CRUD=2, SYSTEM=3.
        """
        items = list(self._commands.values())
        if category is not None:
            cat = category if isinstance(category, CommandCategory) else CommandCategory(category)
            items = [s for s in items if s["category"] == cat]
        items.sort(key=lambda s: (self._CATEGORY_ORDER.get(s["category"], 99), s["name"]))
        return items

    def list_all(self) -> list[dict[str, Any]]:
        return self.list_by_category(None)

    def count(self) -> int:
        return len(self._commands)

    def clear(self) -> None:
        """清空注册表 — 仅用于测试."""
        self._commands.clear()
        self._aliases.clear()

    # ── 工具 ──────────────────────────────────────────

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str):
            raise TypeError(f"name 必须是 str, 收到 {type(name).__name__}")
        n = name.strip().lstrip("/").lower()
        if not n:
            raise ValueError("name 不能为空")
        return n


# ── register_all() — 启动时注册 28 个命令 ──────────────


def register_all(registry: CommandRegistry) -> None:
    """注册全部 28 个命令 — 通过 handler 模块的 *_COMMANDS 列表.

    幂等:重复调用会先清空再注册,避免 ValueError.
    """
    registry.clear()
    from app.commands.handlers.crud import CRUD_COMMANDS
    from app.commands.handlers.dialog import DIALOG_COMMANDS
    from app.commands.handlers.system_ops import SYSTEM_COMMANDS
    from app.commands.handlers.task_control import TASK_CONTROL_COMMANDS

    for spec in (
        *TASK_CONTROL_COMMANDS,
        *DIALOG_COMMANDS,
        *CRUD_COMMANDS,
        *SYSTEM_COMMANDS,
    ):
        registry.register(**spec)


# ── 模块级单例 ──────────────────────────────────────────


registry = CommandRegistry()


def get_default_registry() -> CommandRegistry:
    """返回模块级单例 registry，确保 28 个命令已注册."""
    if not registry._commands:
        register_all(registry)
    return registry
