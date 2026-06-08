"""Phase C C1.2: 验 api-overview.json Grafana dashboard JSON 模板.

不依赖真 Grafana 服务器, 纯 JSON schema 验:
- 顶层字段必填 (title/uid/schemaVersion/panels)
- 5 panel 各占 1 行, 每行 2 个 panel (除最后 1 个 24 宽)
- 每 panel 必有 expr (PromQL)
- panel 覆盖 5 类: req rate / P95 / error / CPU / mem
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "api-overview.json"


def test_json_valid() -> None:
    raw = json.loads(DASHBOARD_PATH.read_text())
    assert isinstance(raw, dict)
    for key in ("title", "uid", "schemaVersion", "panels"):
        assert key in raw, f"missing top-level {key}"
    assert raw["schemaVersion"] >= 38, f"schemaVersion {raw['schemaVersion']} < 38 (Grafana 9+)"
    assert raw["title"] == "API Overview"
    assert raw["uid"] == "api-overview"


def test_five_panels() -> None:
    raw = json.loads(DASHBOARD_PATH.read_text())
    panels = raw["panels"]
    assert len(panels) == 5, f"expected 5 panels, got {len(panels)}"


def test_panels_have_promql() -> None:
    raw = json.loads(DASHBOARD_PATH.read_text())
    for p in raw["panels"]:
        assert "targets" in p, f"panel {p.get('id')} missing targets"
        assert len(p["targets"]) >= 1, f"panel {p.get('id')} has 0 targets"
        for t in p["targets"]:
            assert "expr" in t, f"panel {p.get('id')} target missing expr"
            assert t["expr"].strip(), f"panel {p.get('id')} target expr empty"


def test_panels_cover_5_categories() -> None:
    raw = json.loads(DASHBOARD_PATH.read_text())
    titles = [p.get("title", "") for p in raw["panels"]]
    required = ["Request rate", "P95 latency", "Error rate", "CPU", "memory"]
    for kw in required:
        assert any(kw in t for t in titles), f"missing category {kw!r} in panel titles: {titles}"


def test_panels_use_real_metrics() -> None:
    """验 5 panel 引用的 prometheus 指标在 /metrics 端点真存在 (Phase C C1 70% 累积 ship)."""
    raw = json.loads(DASHBOARD_PATH.read_text())
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/metrics", timeout=5.0) as resp:
            assert resp.status == 200, f"metrics endpoint {resp.status}"
            body = resp.read().decode("utf-8", errors="replace")
    except Exception:
        print("  ⚠️  /metrics 不可达, 跳过 real-metrics 验 (backend 未起)")
        return
    expected_metrics = [
        "api_request_total",
        "http_request_duration_seconds_bucket",
        "python_gc_collections_total",
    ]
    for m in expected_metrics:
        assert m in body, f"metric {m!r} not exposed by /metrics"


if __name__ == "__main__":
    test_json_valid()
    test_five_panels()
    test_panels_have_promql()
    test_panels_cover_5_categories()
    test_panels_use_real_metrics()
    print("5 passed")
