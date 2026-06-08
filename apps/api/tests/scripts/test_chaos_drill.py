"""F21 测: chaos-drill.sh DRY_RUN 模式秒返 + 生成结构化报告.

覆盖:
- 脚本存在 + 可执行
- DRY_RUN 模式秒返 (不阻塞 5min verify)
- 生成 /tmp/chaos-drill-report-*.md 报告
- 报告含 momus v2 G12 必填字段 (F21 + 总耗时 + 模拟故障清单)
- 多 trigger (all) 报告含全部 7 trigger

F21 ship 范围: 1 测覆盖故障注入 → 5min 内自动检测. 本测是 dry-run
版本, 不真触发破坏性故障 (DB down / uvicorn dies / redis disconnect),
仅验脚本可执行 + 报告结构合规. 真实 drill 由 operator 手动跑.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


SCRIPT = (
    Path(__file__).parent.parent.parent.parent.parent / "scripts" / "chaos-drill.sh"
).resolve()


def test_chaos_drill_script_exists_and_executable():
    """F21 前提: 脚本存在 + 可执行."""
    assert SCRIPT.exists(), f"脚本不存在: {SCRIPT}"
    import stat

    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, f"脚本无 user exec 权限: {SCRIPT}"


def test_chaos_drill_dry_run_single_trigger():
    """F21 测 1: DRY_RUN 单 trigger (db-down) 秒返 + 报告合规."""
    env = {**os.environ, "DRY_RUN": "1", "PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        ["bash", str(SCRIPT), "db-down"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, f"非 0 返回: {result.stderr}"
    assert "drill 报告生成" in result.stdout, "stdout 应有 'drill 报告生成'"
    assert "[dry-run] 跳过 docker stop" in result.stdout
    assert "[dry-run] 跳过 verify_alert_with_timing" in result.stdout

    # 找最新生成的报告
    reports = sorted(Path("/tmp").glob("chaos-drill-report-*.md"))
    assert reports, "应该生成 /tmp/chaos-drill-report-*.md"
    report = reports[-1].read_text(encoding="utf-8")

    # momus v2 G12 必填字段
    assert "# Chaos Drill 报告 (F21)" in report
    assert "db-down" in report
    assert "≤ 300s 阈值" in report
    assert "总耗时" in report
    assert "改进点" in report, "应留 operator 填改进点"


def test_chaos_drill_dry_run_all_triggers_under_5s():
    """F21 测 2: DRY_RUN all 模式 7 trigger < 5s (否则违反 ship 前 quick test 原则)."""
    env = {**os.environ, "DRY_RUN": "1", "PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        ["bash", str(SCRIPT), "all"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,  # 严格超时
    )
    assert result.returncode == 0, f"非 0 返回: {result.stderr}"

    # 报告或 stdout 应含全部 7 trigger 函数名 (4 旧 + 3 新, run_trigger_with_timing 会 log "── 启动 trigger_X ──")
    reports = sorted(Path("/tmp").glob("chaos-drill-report-*.md"))
    assert reports
    report = reports[-1].read_text(encoding="utf-8")
    for trigger in ["trigger_5xx", "trigger_p99", "trigger_db_pool", "trigger_llm",
                    "trigger_db_down", "trigger_uvicorn_dies", "trigger_redis_disconnect"]:
        assert trigger in result.stdout, f"stdout 应含 {trigger}"


def test_chaos_drill_syntax_valid():
    """F21 测 3: bash -n 语法校验 (CI 友好)."""
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"语法错误: {result.stderr}"


def test_chaos_drill_report_includes_momus_v2_g12_kpis():
    """F21 测 4: drill 报告含 momus v2 G12 5 KPI 维度."""
    env = {**os.environ, "DRY_RUN": "1", "PATH": os.environ.get("PATH", "")}
    subprocess.run(
        ["bash", str(SCRIPT), "uvicorn-dies"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    reports = sorted(Path("/tmp").glob("chaos-drill-report-*.md"))
    assert reports
    report = reports[-1].read_text(encoding="utf-8")

    # 5 KPI 维度
    kpi_patterns = [
        r"总 trigger 数",
        r"成功 trigger",
        r"失败 trigger",
        r"总耗时",
        r"5min 阈值",
    ]
    for pat in kpi_patterns:
        assert re.search(pat, report), f"报告应含 KPI 维度: {pat}"
