"""隐私脱敏策略配置 (P2-C Stage 13).

提供字段级可配置脱敏策略，支持按环境、按字段名控制脱敏行为。
复用 app/agentops/privacy/sanitizer.py 的底层脱敏能力，但策略可外部配置。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SanitizeAction(StrEnum):
    """脱敏动作。"""

    ALLOW = "allow"              # 原样通过
    MASK = "mask"               # 正则脱敏
    PARTIAL_MASK = "partial_mask"  # 部分遮盖（如 138****1234）
    HASH = "hash"               # SHA-256 哈希
    DROP = "drop"               # 丢弃


# 默认字段级策略（与 sanitizer.py 保持一致）
DEFAULT_FIELD_POLICIES: dict[str, SanitizeAction] = {
    # P0 — 禁止出域
    "resume_text": SanitizeAction.DROP,
    "resume_content": SanitizeAction.DROP,
    "raw_resume": SanitizeAction.DROP,
    "file_url": SanitizeAction.DROP,
    "attachment_url": SanitizeAction.DROP,
    "id_card": SanitizeAction.DROP,
    "identity_card": SanitizeAction.DROP,
    "身份证": SanitizeAction.DROP,
    # P1 — 脱敏后可出
    "phone": SanitizeAction.HASH,
    "mobile": SanitizeAction.HASH,
    "email": SanitizeAction.HASH,
    "candidate_email": SanitizeAction.HASH,
    "candidate_phone": SanitizeAction.HASH,
    "name": SanitizeAction.MASK,
    "candidate_name": SanitizeAction.MASK,
    "contact": SanitizeAction.MASK,
    "address": SanitizeAction.MASK,
    "salary": SanitizeAction.MASK,
    "feedback": SanitizeAction.MASK,
    # P2 — 可出（默认 allow）
    "candidate_id": SanitizeAction.ALLOW,
    "job_id": SanitizeAction.ALLOW,
    "agent_name": SanitizeAction.ALLOW,
    "tool_name": SanitizeAction.ALLOW,
    "model": SanitizeAction.ALLOW,
    "duration_ms": SanitizeAction.ALLOW,
    "score": SanitizeAction.ALLOW,
}

# 环境级别策略覆盖（扩展默认策略）
ENV_POLICY_OVERRIDES: dict[str, dict[str, SanitizeAction]] = {
    "production": {
        "capture_raw_messages": SanitizeAction.DROP,
        "capture_resume_text": SanitizeAction.DROP,
    },
    "development": {
        "capture_raw_messages": SanitizeAction.ALLOW,
    },
}


@dataclass(slots=True)
class PrivacyPolicyConfig:
    """隐私脱敏策略配置。

    Attributes:
        field_policies: 字段名 → 脱敏动作映射。
        env_overrides: 环境名称 → 字段覆盖。
        current_env: 当前环境。
        default_action: 未匹配字段的默认动作。
    """

    field_policies: dict[str, SanitizeAction] = field(default_factory=lambda: dict(DEFAULT_FIELD_POLICIES))
    env_overrides: dict[str, dict[str, SanitizeAction]] = field(
        default_factory=lambda: dict(ENV_POLICY_OVERRIDES)
    )
    current_env: str = "development"
    default_action: SanitizeAction = SanitizeAction.ALLOW

    def get_action(self, field_name: str) -> SanitizeAction:
        """获取某字段的脱敏动作（考虑环境覆盖）。"""
        # 先检查环境覆盖
        env_override = self.env_overrides.get(self.current_env, {})
        key = field_name.lower()
        if key in env_override:
            return env_override[key]
        # 再检查字段策略
        if key in self.field_policies:
            return self.field_policies[key]
        return self.default_action

    def is_dropped(self, field_name: str) -> bool:
        return self.get_action(field_name) == SanitizeAction.DROP

    def is_allowed(self, field_name: str) -> bool:
        return self.get_action(field_name) == SanitizeAction.ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_policies": {k: v.value for k, v in self.field_policies.items()},
            "env_overrides": {
                env: {k: v.value for k, v in overrides.items()}
                for env, overrides in self.env_overrides.items()
            },
            "current_env": self.current_env,
            "default_action": self.default_action.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrivacyPolicyConfig:
        """从 dict 恢复配置。"""
        field_policies = {
            k: SanitizeAction(v) for k, v in data.get("field_policies", {}).items()
        } if data.get("field_policies") else dict(DEFAULT_FIELD_POLICIES)

        env_overrides = {
            env: {k: SanitizeAction(v) for k, v in overrides.items()}
            for env, overrides in data.get("env_overrides", {}).items()
        } if data.get("env_overrides") else dict(ENV_POLICY_OVERRIDES)

        return cls(
            field_policies=field_policies,
            env_overrides=env_overrides,
            current_env=data.get("current_env", "development"),
            default_action=SanitizeAction(data.get("default_action", "allow")),
        )

    def validate(self) -> list[str]:
        """校验配置合法性。"""
        errors: list[str] = []
        valid_actions = set(SanitizeAction)
        for field, action in self.field_policies.items():
            if action not in valid_actions:
                errors.append(f"字段 '{field}' 的脱敏动作 '{action}' 无效")
        for env, overrides in self.env_overrides.items():
            for field, action in overrides.items():
                if action not in valid_actions:
                    errors.append(f"环境 '{env}' 字段 '{field}' 的脱敏动作 '{action}' 无效")
        return errors
