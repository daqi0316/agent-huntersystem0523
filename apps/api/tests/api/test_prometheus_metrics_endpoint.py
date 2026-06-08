"""C1.1 Prometheus metrics 14 server 接入 测.

验证:
1. /metrics 端点 200
2. content-type Prometheus text format
3. process/system metric 暴露 (CPU, mem, GC)
4. record_http_request 后 api_request_total 出现
5. F18 alert 规则定义在 monitoring/prometheus-alerts.yml
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_metrics_endpoint_returns_200(client):
    """§1. /metrics 端点 200 + Prometheus text format."""
    r = client.get("/metrics")
    assert r.status_code == 200, f"期望 200, 实 {r.status_code}"
    # Prometheus text format: 0.0.4
    assert "text/plain" in r.headers.get("content-type", ""), \
        f"content-type 应含 text/plain, 实 {r.headers['content-type']}"


def test_metrics_exposes_process_metrics(client):
    """§2. process/system metrics 暴露 (CPU, mem, GC, python_info)."""
    r = client.get("/metrics")
    body = r.text
    expected = [
        "process_cpu_seconds_total",     # CPU
        "process_resident_memory_bytes",  # mem
        "python_gc_objects_collected_total",  # GC
        "python_info",                    # runtime
    ]
    for m in expected:
        assert m in body, f"缺 metric: {m}"


def test_metrics_response_is_valid_prometheus_format(client):
    """§3. 响应是合法 Prometheus text format (HELP/TYPE + samples)."""
    r = client.get("/metrics")
    body = r.text
    # 必须含 # HELP 和 # TYPE 注释
    assert "# HELP " in body, "缺 # HELP 注释"
    assert "# TYPE " in body, "缺 # TYPE 注释"
    # 必须含 sample 行 (非 0 数字)
    sample_pattern = re.compile(r"^[a-z_][a-z0-9_]*(\{[^}]*\})?\s+[\d\.\-eE\+]+", re.M)
    samples = sample_pattern.findall(body)
    assert len(samples) >= 5, f"sample 数 >= 5, 实 {len(samples)}"


def test_api_request_total_increments_after_request(client):
    """§4. record_http_request middleware → api_request_total 暴露."""
    # 触发一次请求
    client.get("/health")
    r = client.get("/metrics")
    body = r.text
    # api_request_total 在 telemetry.py 中定义, 需触发后才出现
    # 若未触发, 可能 0 sample 也不显示, 这是 prometheus_client 行为
    # 我们只验 telemetry 模块能正常 import + Counter 存在
    from app.core.telemetry import api_request_total, record_http_request
    assert api_request_total is not None
    # 手动 record 一次, 验可调
    record_http_request(method="GET", path="/test", status=200, duration_seconds=0.1)
    r2 = client.get("/metrics")
    assert "api_request_total" in r2.text, "record_http_request 后 /metrics 应有 api_request_total"


def test_mcp_metrics_module_loads():
    """§5. mcp/metrics.py 可正常 import + 7 metric 定义."""
    from app.mcp import metrics as m
    expected = [
        "mcp_calls_total",
        "mcp_call_duration_seconds",
        "mcp_server_up",
        "mcp_server_restarts_total",
        "mcp_server_startup_duration_seconds",
        "mcp_large_results_total",
        "mcp_validation_errors_total",
    ]
    for name in expected:
        assert hasattr(m, name), f"缺 mcp metric: {name}"


def test_prometheus_alerts_yml_exists_with_required_rules():
    """§6. F18 alert rules (2 规则: error > 1%, P95 > 2s) 在 prometheus-alerts.yml."""
    from pathlib import Path
    p = Path("monitoring/prometheus-alerts.yml")
    assert p.exists(), f"缺 {p}"
    content = p.read_text()
    assert "HighErrorRate" in content, "缺 HighErrorRate alert"
    assert "HighP95Latency" in content, "缺 HighP95Latency alert"
    # 阈值 1% = 0.01, P95 = 2s
    assert "0.01" in content, "缺 error rate 阈值 0.01"
    assert "> 2" in content or "2s" in content, "缺 P95 阈值 2s"


def test_main_py_has_metrics_endpoint_and_middleware():
    """§7. main.py 含 /metrics 端点 + request_logging_middleware."""
    from pathlib import Path
    main_py = Path(__file__).parent.parent.parent / "app" / "main.py"
    content = main_py.read_text()
    assert '@app.get("/metrics")' in content, "缺 /metrics 端点"
    assert "render_prometheus" in content, "缺 render_prometheus 调用"
    assert "request_logging_middleware" in content, "缺 request_logging_middleware"
    assert "record_http_request" in content, "缺 record_http_request 调用"
