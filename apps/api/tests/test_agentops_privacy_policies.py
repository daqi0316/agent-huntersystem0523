"""Tests for Privacy Policy Configuration (P2-C Stage 13).

Extends existing test_agentops_sanitizer.py with policy-driven config tests.
"""
from __future__ import annotations

import pytest

from app.agentops.privacy.policies import (
    ENV_POLICY_OVERRIDES,
    PrivacyPolicyConfig,
    SanitizeAction,
)


class TestSanitizeAction:
    def test_all_values_defined(self) -> None:
        assert SanitizeAction.ALLOW == "allow"
        assert SanitizeAction.MASK == "mask"
        assert SanitizeAction.PARTIAL_MASK == "partial_mask"
        assert SanitizeAction.HASH == "hash"
        assert SanitizeAction.DROP == "drop"


class TestPrivacyPolicyConfig:
    def test_default_config(self) -> None:
        cfg = PrivacyPolicyConfig()
        assert cfg.current_env == "development"
        assert cfg.default_action == SanitizeAction.ALLOW
        # P0 字段默认 drop
        assert cfg.get_action("resume_text") == SanitizeAction.DROP
        # P1 字段默认 hash/mask
        assert cfg.get_action("email") == SanitizeAction.HASH
        assert cfg.get_action("phone") == SanitizeAction.HASH
        assert cfg.get_action("name") == SanitizeAction.MASK
        # P2 字段默认 allow
        assert cfg.get_action("tool_name") == SanitizeAction.ALLOW
        # 未知字段默认 allow
        assert cfg.get_action("some_random_field") == SanitizeAction.ALLOW

    def test_env_overrides(self) -> None:
        cfg = PrivacyPolicyConfig(current_env="production")
        # production 环境有额外的 capture_raw_messages = DROP
        assert cfg.get_action("capture_raw_messages") == SanitizeAction.DROP

    def test_env_override_for_development(self) -> None:
        cfg = PrivacyPolicyConfig(current_env="development")
        assert cfg.get_action("capture_raw_messages") == SanitizeAction.ALLOW

    def test_env_override_wins_over_field_policy(self) -> None:
        """环境覆盖优先级高于字段策略。"""
        cfg = PrivacyPolicyConfig(current_env="production")
        # 模拟一个字段在 field_policies 中是 ALLOW，但 env_overrides 中是 DROP
        # 直接修改 env_overrides 验证优先级
        cfg.env_overrides["production"]["email"] = SanitizeAction.DROP
        assert cfg.get_action("email") == SanitizeAction.DROP

    def test_is_dropped(self) -> None:
        cfg = PrivacyPolicyConfig()
        assert cfg.is_dropped("resume_text") is True
        assert cfg.is_dropped("tool_name") is False

    def test_is_allowed(self) -> None:
        cfg = PrivacyPolicyConfig()
        assert cfg.is_allowed("tool_name") is True
        assert cfg.is_allowed("resume_text") is False

    def test_to_dict_roundtrip(self) -> None:
        cfg = PrivacyPolicyConfig(current_env="staging")
        data = cfg.to_dict()
        restored = PrivacyPolicyConfig.from_dict(data)
        assert restored.current_env == "staging"
        assert restored.get_action("email") == cfg.get_action("email")
        assert restored.get_action("resume_text") == cfg.get_action("resume_text")

    def test_from_dict_with_overrides(self) -> None:
        data = {
            "field_policies": {"secret_key": "drop"},
            "env_overrides": {"production": {"secret_key": "mask"}},
            "current_env": "production",
        }
        cfg = PrivacyPolicyConfig.from_dict(data)
        assert cfg.get_action("secret_key") == SanitizeAction.MASK
        assert cfg.current_env == "production"

    def test_custom_field_policy(self) -> None:
        """自定义字段策略。"""
        cfg = PrivacyPolicyConfig(
            field_policies={"my_custom_pii": SanitizeAction.DROP},
            default_action=SanitizeAction.ALLOW,
        )
        assert cfg.get_action("my_custom_pii") == SanitizeAction.DROP
        assert cfg.get_action("other_field") == SanitizeAction.ALLOW

    def test_validate_valid(self) -> None:
        cfg = PrivacyPolicyConfig()
        assert cfg.validate() == []

    def test_validate_invalid_action(self) -> None:
        cfg = PrivacyPolicyConfig()
        # 手动注入非法值
        cfg.field_policies["test"] = "invalid_action"  # type: ignore[assignment]
        errors = cfg.validate()
        assert len(errors) >= 1

    def test_validate_invalid_env_override(self) -> None:
        cfg = PrivacyPolicyConfig()
        cfg.env_overrides["production"] = {"field": "bad_action"}  # type: ignore[assignment]
        errors = cfg.validate()
        assert len(errors) >= 1

    def test_known_p0_fields_mapped(self) -> None:
        cfg = PrivacyPolicyConfig()
        for field in ["resume_text", "resume_content", "raw_resume", "file_url", "id_card"]:
            assert cfg.get_action(field) == SanitizeAction.DROP, f"{field} should be DROP"

    def test_known_p1_fields_mapped(self) -> None:
        cfg = PrivacyPolicyConfig()
        for field in ["email", "phone", "mobile"]:
            assert cfg.get_action(field) == SanitizeAction.HASH, f"{field} should be HASH"
        for field in ["name", "candidate_name", "address", "salary"]:
            assert cfg.get_action(field) == SanitizeAction.MASK, f"{field} should be MASK"

    def test_known_p2_fields_mapped(self) -> None:
        cfg = PrivacyPolicyConfig()
        for field in ["candidate_id", "job_id", "tool_name", "model", "score"]:
            assert cfg.get_action(field) == SanitizeAction.ALLOW, f"{field} should be ALLOW"

    def test_field_name_case_insensitive(self) -> None:
        """get_action 应不区分大小写。"""
        cfg = PrivacyPolicyConfig()
        assert cfg.get_action("EMAIL") == SanitizeAction.HASH
        assert cfg.get_action("Resume_Text") == SanitizeAction.DROP
        assert cfg.get_action("Name") == SanitizeAction.MASK
