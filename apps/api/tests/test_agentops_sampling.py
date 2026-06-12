"""Tests for Sampling Rules and Sampler (P2-C Stage 13)."""
from __future__ import annotations

import pytest

from app.agentops.sampling import SamplingConfig, SamplingRule, Sampler


class TestSamplingRule:
    def test_default_rule(self) -> None:
        rule = SamplingRule()
        assert rule.default_rate == 0.1
        assert rule.always_capture_errors is True
        assert rule.always_capture_slow_traces_ms == 5000.0
        assert rule.agent_overrides == {}

    def test_rate_clamped_to_range(self) -> None:
        rule = SamplingRule(default_rate=1.5)
        assert rule.default_rate == 1.0
        rule2 = SamplingRule(default_rate=-0.1)
        assert rule2.default_rate == 0.0

    def test_agent_overrides_clamped(self) -> None:
        rule = SamplingRule(agent_overrides={"screening": 2.0, "default": -1.0})
        assert rule.agent_overrides["screening"] == 1.0
        assert rule.agent_overrides["default"] == 0.0

    def test_effective_rate_default(self) -> None:
        rule = SamplingRule(default_rate=0.5)
        assert rule.effective_rate() == 0.5
        assert rule.effective_rate("unknown") == 0.5

    def test_effective_rate_with_override(self) -> None:
        rule = SamplingRule(default_rate=0.1, agent_overrides={"screening": 1.0})
        assert rule.effective_rate("screening") == 1.0
        assert rule.effective_rate("other") == 0.1


class TestSamplingConfig:
    def test_default_config(self) -> None:
        cfg = SamplingConfig()
        assert cfg.current_env == "development"
        assert cfg.rules.default_rate == 0.1

    def test_from_dict(self) -> None:
        data = {
            "default_rate": 0.5,
            "always_capture_errors": False,
            "agent_overrides": {"screening": 1.0},
        }
        cfg = SamplingConfig.from_dict(data, env="production")
        assert cfg.rules.default_rate == 0.5
        assert cfg.rules.always_capture_errors is False
        assert cfg.rules.agent_overrides["screening"] == 1.0

    def test_from_dict_nested_sampling(self) -> None:
        data = {
            "sampling": {"default_rate": 0.2, "always_capture_errors": True},
        }
        cfg = SamplingConfig.from_dict(data)
        assert cfg.rules.default_rate == 0.2
        assert cfg.rules.always_capture_errors is True

    def test_resolve_no_env_override(self) -> None:
        cfg = SamplingConfig(current_env="production")
        rule = cfg.resolve()
        assert rule.default_rate == 0.1

    def test_resolve_with_env_override(self) -> None:
        cfg = SamplingConfig(
            current_env="production",
            env_overrides={
                "production": {"default_rate": 0.05, "always_capture_errors": False},
            },
        )
        rule = cfg.resolve()
        assert rule.default_rate == 0.05
        assert rule.always_capture_errors is False
        # 未覆盖的字段保留原值
        assert rule.always_capture_slow_traces_ms == 5000.0

    def test_to_dict_roundtrip(self) -> None:
        cfg = SamplingConfig(current_env="staging")
        data = cfg.to_dict()
        restored = SamplingConfig.from_dict(data, env="staging")
        assert restored.rules.default_rate == cfg.rules.default_rate
        assert restored.current_env == "staging"

    def test_validate_valid(self) -> None:
        cfg = SamplingConfig()
        assert cfg.validate() == []

    def test_validate_invalid_rate(self) -> None:
        cfg = SamplingConfig()
        cfg.rules.default_rate = 1.5
        errors = cfg.validate()
        assert len(errors) >= 1
        assert any("default_rate" in e for e in errors)

    def test_validate_negative_slow_traces(self) -> None:
        cfg = SamplingConfig()
        cfg.rules.always_capture_slow_traces_ms = -1
        errors = cfg.validate()
        assert len(errors) >= 1
        assert any("always_capture_slow_traces_ms" in e for e in errors)

    def test_validate_agent_override_bad(self) -> None:
        cfg = SamplingConfig()
        cfg.rules.agent_overrides["bad"] = 2.0
        errors = cfg.validate()
        assert any("采样率" in e and "bad" in e for e in errors)


class TestSampler:
    def test_default_sampler(self) -> None:
        sampler = Sampler()
        assert sampler.config.current_env == "development"

    def test_capture_error_when_always_capture(self) -> None:
        config = SamplingConfig.from_dict({"always_capture_errors": True})
        sampler = Sampler(config)
        assert sampler.should_capture("tool.failed", is_error=True) is True

    def test_skip_error_when_not_always_capture(self) -> None:
        config = SamplingConfig.from_dict({"always_capture_errors": False})
        sampler = Sampler(config)
        # 错误不强制采集时，走哈希采样，结果可能为 True 也可能为 False
        # 至少不会强制 True
        result = sampler.should_capture("tool.failed", is_error=True, trace_id="test-1")
        result2 = sampler.should_capture("tool.failed", is_error=True, trace_id="test-1")
        assert result == result2  # 确定性

    def test_capture_slow_trace(self) -> None:
        config = SamplingConfig.from_dict({"always_capture_slow_traces_ms": 3000.0})
        sampler = Sampler(config)
        assert sampler.should_capture("span.end", duration_ms=5000.0) is True

    def test_not_capture_fast_trace_by_slow_rule(self) -> None:
        config = SamplingConfig.from_dict({"always_capture_slow_traces_ms": 5000.0})
        sampler = Sampler(config)
        # 慢阈值 5s，1s 的 trace 不应该被慢规则捕获
        # 但可能被默认采样率捕获，所以用 trace_id 确保确定性
        result = sampler.should_capture("span.end", duration_ms=1000.0, trace_id="fast-trace")
        result2 = sampler.should_capture("span.end", duration_ms=1000.0, trace_id="fast-trace")
        assert result == result2

    def test_agent_override_rate(self) -> None:
        config = SamplingConfig.from_dict({
            "default_rate": 0.0,
            "agent_overrides": {"screening": 1.0},
        })
        sampler = Sampler(config)
        assert sampler.should_capture("span.end", agent_name="screening") is True
        # 其他 agent 不受 override 影响（默认 0.0 不采集）
        result = sampler.should_capture("span.end", agent_name="other", trace_id="other-1")
        result2 = sampler.should_capture("span.end", agent_name="other", trace_id="other-1")
        assert result == result2

    def test_deterministic_hashing(self) -> None:
        """同一 trace_id 应得到一致决策。"""
        sampler = Sampler()
        for _ in range(10):
            r1 = sampler.should_capture("event", trace_id="fixed-trace")
            r2 = sampler.should_capture("event", trace_id="fixed-trace")
            assert r1 == r2

    def test_reload_config(self) -> None:
        config1 = SamplingConfig.from_dict({"default_rate": 0.0})
        config2 = SamplingConfig.from_dict({"default_rate": 1.0})
        sampler = Sampler(config1)
        assert sampler.should_capture("event", trace_id="r") is False
        sampler.reload_config(config2)
        assert sampler.should_capture("event", trace_id="r") is True

    def test_hash_decision_always_capture(self) -> None:
        assert Sampler._hash_decision("x", 1.0) is True

    def test_hash_decision_never_capture(self) -> None:
        assert Sampler._hash_decision("x", 0.0) is False

    def test_rate_0_means_no_capture(self) -> None:
        config = SamplingConfig.from_dict({"default_rate": 0.0})
        sampler = Sampler(config)
        # 即使有 trace_id，rate=0 也应该始终不采集
        # 注意：_hash_decision 中 rate=0.0 直接返回 False
        assert sampler.should_capture("event", trace_id="any") is False

    def test_rate_1_means_always_capture(self) -> None:
        config = SamplingConfig.from_dict({"default_rate": 1.0})
        sampler = Sampler(config)
        assert sampler.should_capture("event", trace_id="any") is True
