"""Tests for CommandRegistry — 注册 / 查找 / 别名 / 分类 / 28 命令完整性."""

from __future__ import annotations

from typing import Any

import pytest

from app.commands.registry import CommandRegistry
from app.commands.types import CommandCategory, CommandContext, CommandResult


# ── helpers ────────────────────────────────────────────


async def _noop_handler(args: list[str], flags: dict[str, Any], ctx: CommandContext) -> CommandResult:
    return CommandResult(success=True, message="ok", data={"args": args, "flags": flags})


def _spec(name: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": name,
        "category": CommandCategory.SYSTEM,
        "description": f"test command {name}",
        "handler": _noop_handler,
    }
    base.update(overrides)
    return base


@pytest.fixture
def reg() -> CommandRegistry:
    return CommandRegistry()


# ── register / get ─────────────────────────────────────


def test_register_basic(reg: CommandRegistry) -> None:
    reg.register(_spec("ping"))
    assert reg.has("ping")
    assert reg.get("ping") is not None
    assert reg.get("ping")["name"] == "ping"


def test_register_strips_leading_slash(reg: CommandRegistry) -> None:
    reg.register(_spec("/ping"))
    assert reg.has("ping")
    assert reg.has("/ping")
    assert reg.get("/ping")["name"] == "ping"


def test_register_normalizes_to_lowercase(reg: CommandRegistry) -> None:
    reg.register(_spec("PING"))
    assert reg.has("ping")
    assert reg.has("PING")


def test_register_missing_required_field(reg: CommandRegistry) -> None:
    with pytest.raises(ValueError, match="缺少必填字段"):
        reg.register({"name": "x", "category": CommandCategory.SYSTEM})


def test_register_duplicate_name_raises(reg: CommandRegistry) -> None:
    reg.register(_spec("dup"))
    with pytest.raises(ValueError, match="重复注册"):
        reg.register(_spec("dup"))


def test_register_invalid_category_raises(reg: CommandRegistry) -> None:
    with pytest.raises(ValueError, match="category"):
        reg.register({"name": "x", "category": "system", "handler": _noop_handler})


def test_register_non_callable_handler_raises(reg: CommandRegistry) -> None:
    with pytest.raises(TypeError, match="callable"):
        reg.register({"name": "x", "category": CommandCategory.SYSTEM, "handler": "not callable"})


def test_register_non_dict_raises(reg: CommandRegistry) -> None:
    with pytest.raises(TypeError):
        reg.register("not a dict")  # type: ignore[arg-type]


def test_register_empty_name_raises(reg: CommandRegistry) -> None:
    with pytest.raises(ValueError, match="name 不能为空"):
        reg.register(_spec("  /  "))


# ── 别名 ──────────────────────────────────────────────


def test_alias_resolves_to_canonical(reg: CommandRegistry) -> None:
    reg.register(_spec("restart", aliases=["r"]))
    spec = reg.get("r")
    assert spec is not None
    assert spec["name"] == "restart"
    # alias 自身的 key 也可查
    spec2 = reg.get("R")
    assert spec2 is not None
    assert spec2["name"] == "restart"


def test_alias_conflict_raises(reg: CommandRegistry) -> None:
    reg.register(_spec("a", aliases=["x"]))
    with pytest.raises(ValueError, match="别名"):
        reg.register(_spec("b", aliases=["x"]))


def test_alias_normalized_to_lowercase(reg: CommandRegistry) -> None:
    reg.register(_spec("restart", aliases=["R", "/ReStart"]))
    assert reg.has("r")
    assert reg.has("restart")
    assert reg.get("R")["name"] == "restart"


def test_alias_equal_to_name_ignored(reg: CommandRegistry) -> None:
    """alias 列表包含主名时不应该冲突（会被去重跳过）."""
    reg.register(_spec("dup", aliases=["dup"]))
    assert reg.get("dup")["name"] == "dup"


# ── list_by_category ──────────────────────────────────


def test_list_by_category_filters(reg: CommandRegistry) -> None:
    reg.register(_spec("a", category=CommandCategory.TASK))
    reg.register(_spec("b", category=CommandCategory.DIALOG))
    reg.register(_spec("c", category=CommandCategory.TASK))

    task_cmds = reg.list_by_category(CommandCategory.TASK)
    assert {s["name"] for s in task_cmds} == {"a", "c"}

    dialog_cmds = reg.list_by_category(CommandCategory.DIALOG)
    assert {s["name"] for s in dialog_cmds} == {"b"}

    sys_cmds = reg.list_by_category(CommandCategory.SYSTEM)
    assert sys_cmds == []


def test_list_by_category_accepts_string(reg: CommandRegistry) -> None:
    reg.register(_spec("a", category=CommandCategory.TASK))
    assert len(reg.list_by_category("task")) == 1


def test_list_all_sorted_stable(reg: CommandRegistry) -> None:
    reg.register(_spec("z", category=CommandCategory.TASK))
    reg.register(_spec("a", category=CommandCategory.TASK))
    reg.register(_spec("m", category=CommandCategory.SYSTEM))

    all_cmds = reg.list_all()
    names = [c["name"] for c in all_cmds]
    # 按 (category, name) 排序: system 在 task 之后
    assert names == ["a", "z", "m"]


def test_count_and_clear(reg: CommandRegistry) -> None:
    reg.register(_spec("a"))
    reg.register(_spec("b"))
    assert reg.count() == 2
    reg.clear()
    assert reg.count() == 0
    assert reg.get("a") is None


# ── 31 命令完整性（通过真实 register_all）────────────


def test_register_all_registers_exactly_31_commands() -> None:
    """V.2 退出标准：31 个命令全部注册成功."""
    from app.commands.registry import register_all

    reg = CommandRegistry()
    register_all(reg)
    assert reg.count() == 31, f"期望 31 个, 实际 {reg.count()}"


def test_register_all_covers_4_categories() -> None:
    from app.commands.registry import register_all

    reg = CommandRegistry()
    register_all(reg)
    cats = {s["category"] for s in reg.list_all()}
    assert cats == {
        CommandCategory.TASK,
        CommandCategory.DIALOG,
        CommandCategory.CRUD,
        CommandCategory.SYSTEM,
    }


def test_register_all_category_counts() -> None:
    """每分类 8/8/7/8 分布（与设计文档一致）."""
    from app.commands.registry import register_all

    reg = CommandRegistry()
    register_all(reg)

    expected = {
        CommandCategory.TASK: 8,    # /restart /pause /resume /cancel /retry /rollback /snapshot /checkpoint
        CommandCategory.DIALOG: 8,  # /new /history /switch /back /clear /merge /fork /diff
        CommandCategory.CRUD: 7,    # /read /list /search /write /add /delete /batch
        CommandCategory.SYSTEM: 8,
    }
    for cat, count in expected.items():
        actual = len(reg.list_by_category(cat))
        assert actual == count, f"{cat.value}: 期望 {count}, 实际 {actual}"


def test_register_all_8_aliases() -> None:
    """/r /p /s /h /n /l /d 全部命中."""
    from app.commands.registry import register_all

    reg = CommandRegistry()
    register_all(reg)
    for alias, expected_name in [
        ("r", "restart"),
        ("p", "pause"),
        ("s", "status"),
        ("h", "help"),
        ("n", "new"),
        ("l", "list"),
        ("d", "debug"),
    ]:
        spec = reg.get(alias)
        assert spec is not None, f"alias /{alias} 未注册"
        assert spec["name"] == expected_name, f"/{alias} 应指向 /{expected_name}"
