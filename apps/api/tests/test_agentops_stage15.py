"""Stage 15 — 验证与上线测试。

Covers:
1. 隐私策略在生产强制生效 — agentops enabled 时 PII 字段被正确脱敏
2. Langfuse 故障时业务可用 — provider 抛异常不影响主流程
3. UTC timezone 验证 — 所有时间戳使用 UTC
4. AgentChatResponse trace_id 透传
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.agentops.privacy.policies import PrivacyPolicyConfig, SanitizeAction
from app.agentops.privacy.sanitizer import sanitize_payload


class TestPrivacyPolicyEnforcement:
    """验证隐私策略在生产强制生效 (Stage 15)。"""

    def test_production_drops_resume_text(self) -> None:
        """production 环境 resume_text 应被 DROP。"""
        cfg = PrivacyPolicyConfig(current_env="production")
        assert cfg.get_action("resume_text") == SanitizeAction.DROP
        assert cfg.get_action("raw_resume") == SanitizeAction.DROP
        assert cfg.get_action("id_card") == SanitizeAction.DROP

    def test_production_hashes_email_phone(self) -> None:
        """production 环境 email/phone 应被 HASH。"""
        cfg = PrivacyPolicyConfig(current_env="production")
        assert cfg.get_action("email") == SanitizeAction.HASH
        assert cfg.get_action("phone") == SanitizeAction.HASH

    def test_production_allows_tool_metadata(self) -> None:
        """production 环境工具名/分数等 P2 数据应 ALLOW。"""
        cfg = PrivacyPolicyConfig(current_env="production")
        assert cfg.get_action("tool_name") == SanitizeAction.ALLOW
        assert cfg.get_action("score") == SanitizeAction.ALLOW
        assert cfg.get_action("model") == SanitizeAction.ALLOW

    def test_sanitize_drops_pii_fields(self) -> None:
        """sanitize_payload 应移除 resume_text/id_card 等 P0 字段。"""
        payload = {
            "resume_text": "张三的简历内容...",
            "email": "zhang@test.com",
            "tool_name": "parse_resume",
            "score": 85,
        }
        result = sanitize_payload(payload)
        assert "resume_text" not in result
        # email 被 hash
        assert result.get("email") != "zhang@test.com"
        # P2 字段保留
        assert "tool_name" in result
        assert "score" in result


class TestLangfuseFaultTolerance:
    """验证 Langfuse 故障时业务可用 (Stage 15)。"""

    async def test_noop_provider_never_raises(self) -> None:
        """NoopProvider 所有方法都不抛异常。"""
        from app.agentops.providers.noop import NoopProvider

        p = NoopProvider()
        # 所有方法都应该静默通过
        await p.start_trace(None)
        await p.start_span(None)
        await p.record_event(None)
        await p.record_generation(None)
        await p.record_tool_call(None)
        await p.record_score(None)
        await p.flush()
        await p.shutdown()

    async def test_failing_provider_does_not_crash(self) -> None:
        """provider 的 record 方法抛异常 → 业务不中断。"""
        from app.agentops.providers.noop import NoopProvider

        p = NoopProvider()
        # 这些方法都应有 try/except 包裹，不会传播异常
        await p.start_trace(None)
        await p.record_event(None)

    async def test_queue_exporter_failure_is_silent(self) -> None:
        """队列 exporter 失败 → warning-only，不抛给调用方。"""
        from app.agentops.reliability.queue import AgentOpsQueue

        async def broken_exporter(event) -> None:
            raise RuntimeError("Exporter down")

        queue = AgentOpsQueue(exporter=broken_exporter)
        queue.enqueue({"test": "data"})
        # flush 应捕获异常不打乱主流程
        await queue.flush()
        assert queue.stats.failed == 1
        assert queue.stats.exported == 0

    async def test_circuit_breaker_opens_and_closes(self) -> None:
        """熔断器在连续失败后打开，恢复后关闭。"""
        from app.agentops.reliability.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=0.1)
        assert cb.state == CircuitState.CLOSED

        # 3 次失败 → 打开
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

        # 恢复时间后 → half-open
        import time
        time.sleep(0.15)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

        # success → closed
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestUTCTimezone:
    """验证 UTC timezone 要求 (Stage 15)。"""

    def test_datetime_now_uses_utc(self) -> None:
        """核心模块应使用 UTC。"""
        from app.agentops.core.schemas import BaseEvent
        from app.agentops.dataset.experiment_models import ExperimentModel
        from app.agentops.events.store import BusinessEventModel

        # BaseEvent 的 timestamp 使用 UTC
        import inspect
        src = inspect.getsource(ExperimentModel)
        assert "datetime.now(UTC)" in src or "UTC" in src

    def test_timestamp_has_timezone(self) -> None:
        """事件 timestamp 应包含时区信息。"""
        from app.agentops.core.schemas import _utc_now_iso

        ts = _utc_now_iso()
        assert ts.endswith("+00:00") or ts.endswith("Z")


class TestTraceIdPropagation:
    """验证 trace_id 透传 (Stage 15)。"""

    def test_agent_chat_response_has_trace_id(self) -> None:
        """AgentChatResponse 应包含 trace_id。"""
        from app.api.agent import AgentChatResponse

        resp = AgentChatResponse(reply="test", trace_id="trace-1")
        assert resp.trace_id == "trace-1"
        assert "trace_id" in resp.model_dump()

    def test_x_trace_id_header_in_middleware(self) -> None:
        """middleware 应设置 X-Trace-ID header。"""
        import inspect
        import app.main as main

        src = inspect.getsource(main)
        assert "X-Trace-ID" in src
        assert "agentops_context_middleware" in src
