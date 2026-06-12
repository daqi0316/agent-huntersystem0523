"""Sampler — 运行时采样决策引擎。

基于 SamplingConfig 判断事件是否需要采集。
使用确定性哈希采样（基于 trace_id/event_id），保证同一事件的采样结果稳定。
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.agentops.sampling.rules import SamplingConfig, SamplingRule

logger = logging.getLogger(__name__)


class Sampler:
    """运行时采样决策引擎。

    用法:
        config = SamplingConfig.from_dict({...}, env="production")
        sampler = Sampler(config)
        if sampler.should_capture(event_type="tool.invocation.completed", agent_name="screening"):
            provider.record_event(event)
    """

    def __init__(self, config: SamplingConfig | None = None) -> None:
        self._config = config or SamplingConfig()

    @property
    def config(self) -> SamplingConfig:
        return self._config

    def reload_config(self, config: SamplingConfig) -> None:
        """热更新配置（运行时采样策略变更）。"""
        self._config = config

    def should_capture(
        self,
        event_type: str,
        *,
        agent_name: str | None = None,
        duration_ms: float | None = None,
        is_error: bool = False,
        trace_id: str | None = None,
        **kwargs: Any,
    ) -> bool:
        """判断是否应该采集此事件。

        决策优先级：
        1. 错误事件 + always_capture_errors → True
        2. 慢 trace + always_capture_slow_traces_ms → True
        3. agent override 采样率 → 按率采样
        4. 默认采样率 → 按率采样
        """
        rule = self._config.resolve()

        # 错误全采
        if is_error and rule.always_capture_errors:
            return True

        # 慢请求全采
        if duration_ms is not None and rule.always_capture_slow_traces_ms > 0:
            if duration_ms >= rule.always_capture_slow_traces_ms:
                return True

        # 按 agent override 或默认采样率
        rate = rule.effective_rate(agent_name)
        return self._hash_decision(trace_id or event_type, rate)

    @staticmethod
    def _hash_decision(key: str, rate: float) -> bool:
        """基于 key 的确定性采样决策。

        使用 SHA-256 哈希将 key 映射到 [0, 1) 区间，
        若 hash_ratio < rate 则采集。
        """
        if rate >= 1.0:
            return True
        if rate <= 0.0:
            return False
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        # 取前 8 位十六进制转为 [0, 1) 浮点数
        ratio = int(digest[:8], 16) / 0x10000000  # 0x10000000 = 2^28
        return ratio < rate
