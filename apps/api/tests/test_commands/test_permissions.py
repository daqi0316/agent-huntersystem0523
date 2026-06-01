"""Tests for app.commands.permissions — 4 级权限矩阵 + 工具函数."""

import pytest

from app.commands.permissions import (
    Permission,
    _describe,
    check_permission,
    has_permission,
    require_permission,
)
from app.commands.types import CommandContext


class TestPermissionEnum:
    def test_level_values(self) -> None:
        assert Permission.L1_BASIC == 1
        assert Permission.L2_CONFIRM == 2
        assert Permission.L3_ELEVATED == 3
        assert Permission.L4_ADMIN == 4

    def test_order(self) -> None:
        assert Permission.L1_BASIC < Permission.L4_ADMIN


class TestHasPermission:
    def test_no_permissions_returns_false(self) -> None:
        ok, err = has_permission(Permission.L1_BASIC, None)
        assert not ok
        assert "没有任何权限" in err

    def test_empty_list_returns_false(self) -> None:
        ok, err = has_permission(Permission.L1_BASIC, [])
        assert not ok
        assert "没有任何权限" in err

    def test_sufficient_level_passes(self) -> None:
        ok, err = has_permission(Permission.L2_CONFIRM, ["L2_CONFIRM"])
        assert ok
        assert err is None

    def test_higher_level_implies_lower(self) -> None:
        """隐式授予: 拥有 L4_ADMIN 即拥有 L1~L4 所有权限."""
        ok, err = has_permission(Permission.L1_BASIC, ["L4_ADMIN"])
        assert ok
        ok, err = has_permission(Permission.L2_CONFIRM, ["L4_ADMIN"])
        assert ok
        ok, err = has_permission(Permission.L3_ELEVATED, ["L4_ADMIN"])
        assert ok
        ok, err = has_permission(Permission.L4_ADMIN, ["L4_ADMIN"])
        assert ok

    def test_insufficient_level_returns_false(self) -> None:
        """只有 L1 但要求 L3 → 拒绝."""
        ok, err = has_permission(Permission.L3_ELEVATED, ["L1_BASIC"])
        assert not ok
        assert "权限不足" in err
        assert "L3_ELEVATED" in err

    def test_invalid_permission_name_skipped(self) -> None:
        """列表中有不认识的名字 → 跳过不影响结果."""
        ok, err = has_permission(Permission.L1_BASIC, ["UNKNOWN_PERM", "L2_CONFIRM"])
        assert ok
        assert err is None

    def test_all_invalid_names_returns_false(self) -> None:
        """全是无效名字 → user_max 保持 0 → 拒绝."""
        ok, err = has_permission(Permission.L1_BASIC, ["FOO", "BAR"])
        assert not ok

    def test_user_max_is_tracked_correctly(self) -> None:
        """多个权限取最大值."""
        ok, err = has_permission(Permission.L3_ELEVATED, ["L1_BASIC", "L3_ELEVATED", "L2_CONFIRM"])
        assert ok


class TestDescribe:
    def test_empty_returns_wu(self) -> None:
        assert _describe([]) == "无"

    def test_known_permissions(self) -> None:
        assert _describe(["L1_BASIC", "L3_ELEVATED"]) == "L1_BASIC/L3_ELEVATED"

    def test_unknown_permissions(self) -> None:
        assert _describe(["FOO"]) == "FOO"

    def test_mixed_known_unknown(self) -> None:
        assert _describe(["L1_BASIC", "FOO"]) == "L1_BASIC/FOO"


class TestRequirePermission:
    async def test_sets_metadata(self) -> None:
        async def dummy(args, flags, ctx):
            return None
        decorated = require_permission(Permission.L3_ELEVATED)(dummy)
        assert decorated.__permission_level__ == Permission.L3_ELEVATED


class TestCheckPermission:
    def test_single_permission_passes(self) -> None:
        ctx = CommandContext(user_id="u", session_id="s", permissions=["L3_ELEVATED"])
        ok, err = check_permission(Permission.L2_CONFIRM, ctx)
        assert ok

    def test_single_permission_denies(self) -> None:
        ctx = CommandContext(user_id="u", session_id="s", permissions=["L1_BASIC"])
        ok, err = check_permission(Permission.L3_ELEVATED, ctx)
        assert not ok

    def test_list_or_permission_passes(self) -> None:
        """OR 语义: 满足任一即通过."""
        ctx = CommandContext(user_id="u", session_id="s", permissions=["L1_BASIC"])
        ok, err = check_permission([Permission.L3_ELEVATED, Permission.L1_BASIC], ctx)
        assert ok

    def test_list_or_permission_denies(self) -> None:
        """OR 语义: 都不满足才拒绝."""
        ctx = CommandContext(user_id="u", session_id="s", permissions=["L1_BASIC"])
        ok, err = check_permission([Permission.L3_ELEVATED, Permission.L4_ADMIN], ctx)
        assert not ok

    def test_empty_required_always_passes(self) -> None:
        ctx = CommandContext(user_id="u", session_id="s", permissions=[])
        ok, err = check_permission([], ctx)
        assert ok
