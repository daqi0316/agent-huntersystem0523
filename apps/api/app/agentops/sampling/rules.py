"""采样规则配置 (P2-C Stage 13).

定义:
- SamplingRule: 单条规则，含默认采样率、错误全采、慢 trace 阈值、agent 级别覆盖
- SamplingConfig: 规则集合，支持按环境覆盖

配置示例:
    sampling:
      default_rate: 0.1
      always_capture_errors: true
      always_capture_slow_traces_ms: 5000
      agent_overrides:
        screening: 1.0
        onboarding: 0.3
      env_overrides:
        production:
          default_rate: 0.05
        development:
          default_rate: 1.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SamplingRule:
    """单条采样规则。

    Attributes:
        default_rate: 默认采样率 [0.0, 1.0]，1.0 = 全采。
        always_capture_errors: 错误事件是否全量采集。
        always_capture_slow_traces_ms: 超过此阈值(ms)的 trace 全采；0=不启用。
        agent_overrides: 按 agent 名称覆盖采样率。
    """

    default_rate: float = 0.1
    always_capture_errors: bool = True
    always_capture_slow_traces_ms: float = 5000.0
    agent_overrides: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.default_rate = max(0.0, min(1.0, self.default_rate))
        for k, v in self.agent_overrides.items():
            self.agent_overrides[k] = max(0.0, min(1.0, v))

    def effective_rate(self, agent_name: str | None = None) -> float:
        """获取生效的采样率，支持 agent 级别覆盖。"""
        if agent_name and agent_name in self.agent_overrides:
            return self.agent_overrides[agent_name]
        return self.default_rate


@dataclass(slots=True)
class SamplingConfig:
    """采样配置集合，支持按环境覆盖。

    Attributes:
        rules: 默认的采样规则。
        env_overrides: 按环境名称覆盖规则字段。
        current_env: 当前运行环境 (prod/staging/development/test)。
    """

    rules: SamplingRule = field(default_factory=SamplingRule)
    env_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    current_env: str = "development"

    class ValidationError(ValueError):
        """配置校验错误。"""

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, env: str = "development") -> SamplingConfig:
        """从 dict 创建配置（通常来自 YAML/config）。"""
        rules_data = data.get("sampling", data)  # 支持根级或 sampling 嵌套
        rule = SamplingRule(
            default_rate=rules_data.get("default_rate", 0.1),
            always_capture_errors=rules_data.get("always_capture_errors", True),
            always_capture_slow_traces_ms=rules_data.get("always_capture_slow_traces_ms", 5000.0),
            agent_overrides=rules_data.get("agent_overrides", {}),
        )
        return cls(
            rules=rule,
            env_overrides=data.get("env_overrides", {}),
            current_env=env,
        )

    def resolve(self) -> SamplingRule:
        """解析当前环境的最终规则（基础规则 + 环境覆盖）。"""
        if self.current_env not in self.env_overrides:
            return self.rules

        overrides = self.env_overrides[self.current_env]
        merged = SamplingRule(
            default_rate=overrides.get("default_rate", self.rules.default_rate),
            always_capture_errors=overrides.get("always_capture_errors", self.rules.always_capture_errors),
            always_capture_slow_traces_ms=overrides.get(
                "always_capture_slow_traces_ms", self.rules.always_capture_slow_traces_ms
            ),
            agent_overrides=overrides.get("agent_overrides", dict(self.rules.agent_overrides)),
        )
        return merged

    def validate(self) -> list[str]:
        """校验配置合法性，返回错误列表（空 = 合法）。"""
        errors: list[str] = []
        if not (0.0 <= self.rules.default_rate <= 1.0):
            errors.append(f"default_rate {self.rules.default_rate} 不在 [0, 1] 范围内")
        if self.rules.always_capture_slow_traces_ms < 0:
            errors.append(f"always_capture_slow_traces_ms ({self.rules.always_capture_slow_traces_ms}) 不能为负")
        for agent, rate in self.rules.agent_overrides.items():
            if not (0.0 <= rate <= 1.0):
                errors.append(f"agent '{agent}' 采样率 {rate} 不在 [0, 1] 范围内")
        return errors

    def to_dict(self) -> dict[str, Any]:
        """导出配置为可序列化 dict。"""
        return {
            "sampling": {
                "default_rate": self.rules.default_rate,
                "always_capture_errors": self.rules.always_capture_errors,
                "always_capture_slow_traces_ms": self.rules.always_capture_slow_traces_ms,
                "agent_overrides": dict(self.rules.agent_overrides),
            },
            "env_overrides": dict(self.env_overrides),
            "current_env": self.current_env,
        }
