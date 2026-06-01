"""Permission Isolation — Agent 操作的角色级权限控制。

角色层级:
  admin   -> 全部操作
  hr      -> 核心招聘流程（筛选/面试/Offer/入职）
  recruiter -> 执行层（筛选/面试/寻源）
  viewer  -> 只读（查看候选人/报告/仪表盘）
"""

from __future__ import annotations

from app.models.user import UserRole

AGENT_PERMISSIONS: dict[str, set[UserRole]] = {
    "view_candidate": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER, UserRole.VIEWER},
    "create_candidate": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER},
    "update_candidate": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER},
    "delete_candidate": {UserRole.ADMIN},
    "export_candidate": {UserRole.ADMIN, UserRole.HR},
    "screen_resume": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER},
    "view_screening_result": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER, UserRole.VIEWER},
    "batch_screen": {UserRole.ADMIN, UserRole.HR},
    "schedule_interview": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER},
    "confirm_interview": {UserRole.ADMIN, UserRole.HR},
    "cancel_interview": {UserRole.ADMIN, UserRole.HR},
    "complete_interview": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER},
    "evaluate_interview": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER},
    "view_interview": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER, UserRole.VIEWER},
    "generate_jd": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER},
    "search_candidate": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER},
    "talent_map": {UserRole.ADMIN, UserRole.HR},
    "create_offer": {UserRole.ADMIN, UserRole.HR},
    "approve_offer": {UserRole.ADMIN},
    "send_offer": {UserRole.ADMIN, UserRole.HR},
    "view_offer": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER, UserRole.VIEWER},
    "create_onboarding_plan": {UserRole.ADMIN, UserRole.HR},
    "update_onboarding": {UserRole.ADMIN, UserRole.HR},
    "probation_review": {UserRole.ADMIN, UserRole.HR},
    "view_report": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER, UserRole.VIEWER},
    "view_analytics": {UserRole.ADMIN, UserRole.HR},
    "export_report": {UserRole.ADMIN, UserRole.HR},
    "manage_users": {UserRole.ADMIN},
    "manage_settings": {UserRole.ADMIN},
    "view_audit_log": {UserRole.ADMIN, UserRole.HR},
    "run_agent": {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER},
    "manage_agent": {UserRole.ADMIN},
}


def check_permission(role: UserRole | str, action: str) -> bool:
    """检查角色是否有权执行指定操作。"""
    if isinstance(role, str):
        try:
            role = UserRole(role)
        except ValueError:
            return False
    allowed = AGENT_PERMISSIONS.get(action, set())
    return role in allowed


def require_permission(role: UserRole | str, action: str) -> None:
    """检查权限，失败时抛出 PermissionError。"""
    if not check_permission(role, action):
        role_str = role.value if isinstance(role, UserRole) else str(role)
        allowed_roles = [r.value for r in AGENT_PERMISSIONS.get(action, set())]
        raise PermissionError(
            f"角色 '{role_str}' 无权执行 '{action}'。需要角色: {allowed_roles}"
        )
