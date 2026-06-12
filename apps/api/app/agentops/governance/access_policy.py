"""访问控制策略 (P2-C Stage 13).

定义角色级可见性策略，控制不同角色可以查看哪些数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class VisibilityLevel(StrEnum):
    """可见性级别，从宽到严。"""

    ALL = "all"                         # 全部数据
    TENANT = "tenant"                   # 本租户数据
    ENVIRONMENT = "environment"         # 本环境数据
    OWN = "own"                         # 仅自己创建的数据
    NONE = "none"                       # 无权限


# 角色 → 可见性级别默认映射
DEFAULT_ROLE_VISIBILITY: dict[str, VisibilityLevel] = {
    "admin": VisibilityLevel.ALL,
    "operator": VisibilityLevel.ENVIRONMENT,
    "engineer": VisibilityLevel.TENANT,
    "viewer": VisibilityLevel.TENANT,
    "auditor": VisibilityLevel.ALL,     # 只读
}


@dataclass(slots=True)
class AccessPolicyRule:
    """单条访问控制规则。

    Attributes:
        role: 角色名称。
        visibility: 可见性级别。
        resources: 可访问的资源类型列表 (空 = 全部)。
        max_score_detail: 最大可查看的 score 详细级别 (None = 全部)。
    """

    role: str
    visibility: VisibilityLevel = VisibilityLevel.TENANT
    resources: list[str] = field(default_factory=list)
    max_score_detail: str | None = None


@dataclass(slots=True)
class AccessPolicy:
    """访问控制策略集合。"""

    rules: dict[str, AccessPolicyRule] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 若未初始化，填充默认规则
        if not self.rules:
            for role, vis in DEFAULT_ROLE_VISIBILITY.items():
                self.rules[role] = AccessPolicyRule(role=role, visibility=vis)

    def get_visibility(self, role: str) -> VisibilityLevel:
        rule = self.rules.get(role)
        return rule.visibility if rule else DEFAULT_ROLE_VISIBILITY.get(role, VisibilityLevel.NONE)

    def can_access(self, role: str, resource: str) -> bool:
        """检查角色是否有权访问某资源。"""
        rule = self.rules.get(role)
        if rule is None:
            return False
        if not rule.resources:
            return True  # 空列表 = 全部
        return resource in rule.resources

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {
            r.role: {
                "visibility": r.visibility.value,
                "resources": r.resources,
                "max_score_detail": r.max_score_detail,
            }
            for r in self.rules.values()
        }


def check_access(
    policy: AccessPolicy,
    role: str,
    resource: str,
    *,
    require_visibility: VisibilityLevel | None = None,
) -> bool:
    """快捷访问检查。

    同时检查资源权限和可见性级别。
    """
    if not policy.can_access(role, resource):
        return False
    if require_visibility:
        actual = policy.get_visibility(role)
        # 按枚举定义顺序比较：ALL(0) > TENANT(1) > ENVIRONMENT(2) > OWN(3) > NONE(4)
        levels = list(VisibilityLevel)
        if levels.index(actual) > levels.index(require_visibility):
            return False
    return True
