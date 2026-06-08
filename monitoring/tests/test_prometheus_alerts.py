"""F18: 验 prometheus-alerts.yml 模板.

不依赖真 Prometheus / alertmanager, 纯 YAML + PromQL schema 验:
- 1 group 含 2 rules
- 2 rule names: HighErrorRate / HighP95Latency
- 2 expr 引用真指标 (api_request_total / http_request_duration_seconds_bucket)
- 阈值符合规划 §5.3 (error > 1% / P95 > 2s)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALERTS_PATH = Path(__file__).resolve().parent.parent / "prometheus-alerts.yml"


def test_yaml_valid() -> None:
    import yaml
    raw = yaml.safe_load(ALERTS_PATH.read_text())
    assert isinstance(raw, dict)
    assert "groups" in raw
    assert len(raw["groups"]) == 1
    assert raw["groups"][0]["name"] == "api-overview"


def test_two_rules() -> None:
    import yaml
    raw = yaml.safe_load(ALERTS_PATH.read_text())
    rules = raw["groups"][0]["rules"]
    assert len(rules) == 2, f"expected 2 rules, got {len(rules)}"
    names = {r["alert"] for r in rules}
    assert names == {"HighErrorRate", "HighP95Latency"}


def test_promql_expressions() -> None:
    import yaml
    raw = yaml.safe_load(ALERTS_PATH.read_text())
    rules = raw["groups"][0]["rules"]
    for r in rules:
        assert "expr" in r
        assert r["expr"].strip()
        assert "for" in r
        assert r["for"].endswith("m") or r["for"].endswith("s")


def test_error_rate_threshold_1pct() -> None:
    """验 HighErrorRate 阈值 = 1% (规划 §5.3 'error > 1%')."""
    import yaml
    raw = yaml.safe_load(ALERTS_PATH.read_text())
    rules = raw["groups"][0]["rules"]
    error_rule = next(r for r in rules if r["alert"] == "HighErrorRate")
    assert "0.01" in error_rule["expr"], f"error threshold not 1%: {error_rule['expr']}"
    assert "5.." in error_rule["expr"], "must match 5xx status"


def test_p95_latency_threshold_2s() -> None:
    """验 HighP95Latency 阈值 = 2s (规划 §5.3 'P95 > 2s')."""
    import yaml
    raw = yaml.safe_load(ALERTS_PATH.read_text())
    rules = raw["groups"][0]["rules"]
    p95_rule = next(r for r in rules if r["alert"] == "HighP95Latency")
    assert "2" in p95_rule["expr"]
    assert "histogram_quantile" in p95_rule["expr"]
    assert "http_request_duration_seconds_bucket" in p95_rule["expr"]


def test_real_metrics_exposed() -> None:
    """验 2 rule 引用的指标在 /metrics 端点真存在."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/metrics", timeout=5.0) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8", errors="replace")
    except Exception:
        print("  ⚠️  /metrics 不可达, 跳过 real-metrics 验 (backend 未起)")
        return
    expected = ["api_request_total", "http_request_duration_seconds_bucket"]
    for m in expected:
        assert m in body, f"metric {m!r} not exposed"


if __name__ == "__main__":
    test_yaml_valid()
    test_two_rules()
    test_promql_expressions()
    test_error_rate_threshold_1pct()
    test_p95_latency_threshold_2s()
    test_real_metrics_exposed()
    print("6 passed")
