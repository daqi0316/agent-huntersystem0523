"""Tests for Permissions — role-based access control for agent operations."""

import pytest

from app.models.user import UserRole
from app.agents.permissions import AGENT_PERMISSIONS, check_permission, require_permission


def test_all_actions_have_roles():
    """Every action must have at least one role assigned."""
    for action, roles in AGENT_PERMISSIONS.items():
        assert len(roles) > 0, f"Action '{action}' has no roles"


def test_admin_has_all_permissions():
    for action in AGENT_PERMISSIONS:
        assert check_permission(UserRole.ADMIN, action), f"Admin should have '{action}'"


def test_viewer_limited():
    assert check_permission(UserRole.VIEWER, "view_candidate") is True
    assert check_permission(UserRole.VIEWER, "create_candidate") is False
    assert check_permission(UserRole.VIEWER, "delete_candidate") is False
    assert check_permission(UserRole.VIEWER, "manage_users") is False


def test_hr_can_screen_and_interview():
    assert check_permission(UserRole.HR, "screen_resume") is True
    assert check_permission(UserRole.HR, "schedule_interview") is True
    assert check_permission(UserRole.HR, "create_offer") is True
    assert check_permission(UserRole.HR, "view_report") is True


def test_recruiter_cannot_admin():
    assert check_permission(UserRole.RECRUITER, "manage_users") is False
    assert check_permission(UserRole.RECRUITER, "delete_candidate") is False
    assert check_permission(UserRole.RECRUITER, "approve_offer") is False
    assert check_permission(UserRole.RECRUITER, "batch_screen") is False


def test_unknown_action_returns_false():
    assert check_permission(UserRole.ADMIN, "non_existent_action") is False


def test_unknown_role_returns_false():
    assert check_permission("super_admin", "view_candidate") is False


def test_require_permission_passes():
    require_permission(UserRole.ADMIN, "manage_users")  # should not raise


def test_require_permission_raises():
    with pytest.raises(PermissionError) as exc:
        require_permission(UserRole.VIEWER, "manage_users")
    assert "无权" in str(exc.value)


def test_require_permission_string_role():
    require_permission("admin", "manage_users")  # should not raise


def test_require_permission_string_role_failure():
    with pytest.raises(PermissionError):
        require_permission("viewer", "manage_users")


def test_admin_deletion():
    assert check_permission(UserRole.ADMIN, "delete_candidate") is True
    assert check_permission(UserRole.HR, "delete_candidate") is False
    assert check_permission(UserRole.RECRUITER, "delete_candidate") is False


def test_offer_approval_restricted():
    assert check_permission(UserRole.ADMIN, "approve_offer") is True
    assert check_permission(UserRole.HR, "approve_offer") is False
    assert check_permission(UserRole.RECRUITER, "approve_offer") is False


def test_analytics_restricted():
    assert check_permission(UserRole.ADMIN, "view_analytics") is True
    assert check_permission(UserRole.HR, "view_analytics") is True
    assert check_permission(UserRole.RECRUITER, "view_analytics") is False
    assert check_permission(UserRole.VIEWER, "view_analytics") is False


def test_talent_map_restricted():
    assert check_permission(UserRole.ADMIN, "talent_map") is True
    assert check_permission(UserRole.HR, "talent_map") is True
    assert check_permission(UserRole.RECRUITER, "talent_map") is False
