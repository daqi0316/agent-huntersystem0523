"""Phase A 推后 (3): test compare_with_baseline 纯函数.

不依赖 backend / MCP server / HTTP, 只验 diff 算 + 阈值标 (ok/warning/critical/new).
"""

from __future__ import annotations

import sys
from pathlib import Path

# 让脚本可 import (scripts/perf_baseline.py)
_SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS))

from perf_baseline import BaselineResult, compare_with_baseline  # noqa: E402


def _r(target: str, p50: float, p95: float, p99: float) -> BaselineResult:
    return BaselineResult(
        category="mcp_cold_start",
        target=target,
        rounds=1,
        trials=10,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
    )


def test_ok_within_20pct() -> None:
    """P50/P95/P99 都 ±20% 内 → status ok."""
    cur = [_r("utils_server", 100, 120, 150)]
    base = [_r("utils_server", 105, 115, 145)]
    diffs = compare_with_baseline(cur, base)
    assert len(diffs) == 1
    assert diffs[0]["status"] == "ok"
    assert abs(diffs[0]["p95_delta_pct"]) < 20


def test_warning_20_to_50pct() -> None:
    """P95 退化 25% → status warning."""
    cur = [_r("utils_server", 100, 125, 150)]
    base = [_r("utils_server", 100, 100, 150)]
    diffs = compare_with_baseline(cur, base)
    assert diffs[0]["status"] == "warning"
    assert 20 <= abs(diffs[0]["p95_delta_pct"]) < 50


def test_critical_above_50pct() -> None:
    """P95 退化 60% → status critical."""
    cur = [_r("utils_server", 100, 160, 200)]
    base = [_r("utils_server", 100, 100, 200)]
    diffs = compare_with_baseline(cur, base)
    assert diffs[0]["status"] == "critical"
    assert abs(diffs[0]["p95_delta_pct"]) >= 50


def test_new_target_no_baseline() -> None:
    """当前有新 target, baseline 没 → status new."""
    cur = [_r("new_server", 100, 120, 150)]
    base = [_r("old_server", 100, 120, 150)]
    diffs = compare_with_baseline(cur, base)
    assert diffs[0]["status"] == "new"
    assert diffs[0]["target"] == "new_server"


def test_zero_baseline_safe() -> None:
    """baseline P95=0 (历史空数据) → 不除零, current=0 → 0%, current>0 → 100%."""
    cur = [_r("utils_server", 0, 0, 0)]
    base = [_r("utils_server", 0, 0, 0)]
    diffs = compare_with_baseline(cur, base)
    assert diffs[0]["status"] == "ok"

    cur2 = [_r("utils_server", 100, 120, 150)]
    base2 = [_r("utils_server", 0, 0, 0)]
    diffs2 = compare_with_baseline(cur2, base2)
    assert diffs2[0]["p95_delta_pct"] == 100.0
    assert diffs2[0]["status"] == "critical"


def test_improvement_negative_delta() -> None:
    """性能改善 (P95 减少 30%) → 仍 ok (退化阈值, 改善不算 critical)."""
    cur = [_r("utils_server", 100, 70, 90)]
    base = [_r("utils_server", 100, 100, 90)]
    diffs = compare_with_baseline(cur, base)
    assert diffs[0]["p95_delta_pct"] < 0
    assert diffs[0]["status"] == "ok"


if __name__ == "__main__":
    test_ok_within_20pct()
    test_warning_20_to_50pct()
    test_critical_above_50pct()
    test_new_target_no_baseline()
    test_zero_baseline_safe()
    test_improvement_negative_delta()
    print("6 passed")
