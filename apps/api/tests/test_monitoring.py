"""P5-7: 监控告警 tests (telemetry metrics + 告警引擎 + path normalize)。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


class TestAlertRulesConfig:
    def test_5_alert_rules(self):
        from app.core.telemetry import ALERT_RULES
        assert len(ALERT_RULES) == 5

    def test_5xx_rule_threshold(self):
        from app.core.telemetry import ALERT_RULES
        rule = next(r for r in ALERT_RULES if r["name"] == "http_5xx_rate_high")
        assert rule["threshold"] == 0.005
        assert rule["window_seconds"] == 60
        assert rule["severity"] == "P1"

    def test_p99_rule_threshold(self):
        from app.core.telemetry import ALERT_RULES
        rule = next(r for r in ALERT_RULES if r["name"] == "http_p99_latency_high")
        assert rule["threshold_p99_seconds"] == 2.0
        assert rule["window_seconds"] == 60

    def test_db_pool_rule(self):
        from app.core.telemetry import ALERT_RULES
        rule = next(r for r in ALERT_RULES if r["name"] == "db_pool_high")
        assert rule["threshold"] == 0.80

    def test_llm_failure_rule(self):
        from app.core.telemetry import ALERT_RULES
        rule = next(r for r in ALERT_RULES if r["name"] == "llm_failure_rate_high")
        assert rule["threshold"] == 0.05
        assert rule["window_seconds"] == 300

    def test_llm_quota_rule_p2(self):
        from app.core.telemetry import ALERT_RULES
        rule = next(r for r in ALERT_RULES if r["name"] == "llm_token_quota_low")
        assert rule["severity"] == "P2"
        assert rule["threshold"] == 0.20


class TestPathNormalize:
    def test_uuid_path_normalized(self):
        from app.core.telemetry import _normalize_path
        uuid = "abc12345-1234-1234-1234-abc123456789"
        assert _normalize_path(f"/candidates/{uuid}") == "/candidates/:id"

    def test_numeric_path_normalized(self):
        from app.core.telemetry import _normalize_path
        assert _normalize_path("/jobs/42") == "/jobs/:n"

    def test_static_path_unchanged(self):
        from app.core.telemetry import _normalize_path
        assert _normalize_path("/api/v1/auth/login") == "/api/v1/auth/login"

    def test_query_string_stripped(self):
        from app.core.telemetry import _normalize_path
        assert _normalize_path("/candidates/abc12345-1234-1234-1234-abc123456789?foo=bar") == "/candidates/:id"

    def test_path_truncated_128(self):
        from app.core.telemetry import _normalize_path
        long = "/" + "a" * 200
        result = _normalize_path(long)
        assert len(result) <= 128


class TestRecordHttpRequest:
    def test_record_http_request_2xx_no_5xx_inc(self):
        from app.core import telemetry
        before_5xx = telemetry.http_5xx_total.labels(method="GET", path="/test_2xx")._value.get()
        telemetry.record_http_request(method="GET", path="/test_2xx", status=200, duration_seconds=0.1)
        after_5xx = telemetry.http_5xx_total.labels(method="GET", path="/test_2xx")._value.get()
        assert after_5xx == before_5xx

    def test_record_http_request_5xx_inc(self):
        from app.core import telemetry
        before_5xx = telemetry.http_5xx_total.labels(method="POST", path="/test_5xx")._value.get()
        telemetry.record_http_request(method="POST", path="/test_5xx", status=500, duration_seconds=0.1)
        after_5xx = telemetry.http_5xx_total.labels(method="POST", path="/test_5xx")._value.get()
        assert after_5xx == before_5xx + 1

    def test_record_http_request_observes_histogram(self):
        from app.core import telemetry
        before_count = telemetry.http_request_duration_seconds.labels(method="GET", path="/test_hist")._sum.get()
        telemetry.record_http_request(method="GET", path="/test_hist", status=200, duration_seconds=0.123)
        after_count = telemetry.http_request_duration_seconds.labels(method="GET", path="/test_hist")._sum.get()
        assert after_count == before_count + 0.123


class TestRecordLLMCall:
    def test_record_llm_call_success(self):
        from app.core import telemetry
        before = telemetry.llm_request_total.labels(model="qwen3.6", status="success")._value.get()
        telemetry.record_llm_call(model="qwen3.6", prompt_tokens=100, completion_tokens=50, success=True)
        after = telemetry.llm_request_total.labels(model="qwen3.6", status="success")._value.get()
        assert after == before + 1

    def test_record_llm_call_failure(self):
        from app.core import telemetry
        before = telemetry.llm_failure_total.labels(model="qwen3.6", error_type="timeout")._value.get()
        telemetry.record_llm_call(model="qwen3.6", prompt_tokens=100, completion_tokens=0, success=False, error_type="timeout")
        after = telemetry.llm_failure_total.labels(model="qwen3.6", error_type="timeout")._value.get()
        assert after == before + 1

    def test_record_llm_token_increments(self):
        from app.core import telemetry
        before = telemetry.llm_token_total.labels(model="qwen3.6", kind="prompt")._value.get()
        telemetry.record_llm_call(model="qwen3.6", prompt_tokens=500, completion_tokens=200, success=True)
        after = telemetry.llm_token_total.labels(model="qwen3.6", kind="prompt")._value.get()
        assert after == before + 500


class TestDBPoolMetrics:
    def test_update_db_pool_metrics(self):
        from app.core import telemetry
        telemetry.update_db_pool_metrics(used=8, size=10)
        assert telemetry.db_pool_used._value.get() == 8
        assert telemetry.db_pool_size._value.get() == 10


class TestSlidingWindow:
    def test_sliding_window_rate(self):
        from app.core.telemetry import _SlidingWindow
        w = _SlidingWindow()
        for v in [0, 0, 0, 1, 1]:
            w.add(v)
        assert w.rate_within(60, lambda v: v > 0) == 2

    def test_sliding_window_p99(self):
        from app.core.telemetry import _SlidingWindow
        w = _SlidingWindow()
        for v in [0.1, 0.2, 0.3, 5.0, 10.0]:
            w.add(v)
        p99 = w.p99_within(60)
        assert p99 is not None
        assert p99 >= 0.1


class TestCheckAlerts:
    @pytest.mark.asyncio
    async def test_no_alerts_when_empty(self):
        from app.core.telemetry import check_alerts
        from app.core import telemetry
        telemetry._5xx_window.samples.clear()
        telemetry._latency_window.samples.clear()
        alerts = await check_alerts()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_alert_5xx_rate(self):
        from app.core.telemetry import check_alerts
        from app.core import telemetry
        telemetry._5xx_window.samples.clear()
        for _ in range(100):
            telemetry._5xx_window.add(1.0)
        alerts = await check_alerts()
        names = [a["name"] for a in alerts]
        assert "http_5xx_rate_high" in names


class TestSentrySetup:
    def test_sentry_disabled_without_dsn(self):
        import os
        from app.core.sentry_setup import init_sentry
        old = os.environ.pop("SENTRY_DSN", None)
        try:
            assert init_sentry() is False
        finally:
            if old:
                os.environ["SENTRY_DSN"] = old

    def test_sentry_pii_scrub_email(self):
        from app.core.sentry_setup import _scrub_pii
        event = {
            "request": {"data": {"email": "test@x.com", "name": "T"}},
            "user": {"email": "u@x.com"},
            "extra": {"password": "p"},
        }
        scrubbed = _scrub_pii(event, None)
        assert scrubbed["request"]["data"]["email"] == "[redacted]"
        assert scrubbed["request"]["data"]["name"] == "[redacted]"
        assert scrubbed["user"]["email"] == "[redacted]"
        assert scrubbed["extra"]["password"] == "[redacted]"


class TestPrometheusRender:
    def test_render_prometheus_returns_bytes(self):
        from app.core.telemetry import render_prometheus
        body, content_type = render_prometheus()
        assert isinstance(body, bytes)
        assert "text/plain" in content_type

    def test_render_includes_new_metrics(self):
        from app.core.telemetry import render_prometheus, record_http_request
        record_http_request("GET", "/render_test", 200, 0.1)
        body, _ = render_prometheus()
        body_str = body.decode("utf-8")
        assert "http_request_duration_seconds" in body_str
        assert "http_5xx_total" in body_str
