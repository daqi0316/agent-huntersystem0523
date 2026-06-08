"""F12 教训沉淀: NAME_PATTERN 改不破坏老 ship report 测.

背景: F12 (178865f) 加 followup-* 到 NAME_PATTERN 时暴露 14 老 followup-*
ship report 不合规 5 强约束. CI 必 fail 老 ship report.

教训: 任何 NAME_PATTERN 改 (扩 family) 必须先验现有文件不 fail.

本测锁当前 pass 数基线 15 (11 mcp-v4-v1.4 + 4 followup-* 新模板),
任何未来 NAME_PATTERN / 5 强约束 / 9 章节检查逻辑改必保持 pass 数 >= 15
(等量老 ship report). 若 pass 数下降 → 测 fail → CI block → 防 F12-style
critical bug 再发.

更新基线: 新 ship report ship 时手动 +1, 推到 16/17/... (存量增长,
不减).

实现: subprocess 跑 CLI (不 import), 跟 test_chaos_drill.py 同模式,
避免 module 路径/PYTHONPATH 差异导致 pass 数 0/51 vs 15/36 的诡异
不一致.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


# F12 baseline: 15 ship report pass (11 mcp-v4-v1.4 + 4 followup-* 新模板)
# F retrofit (3 retrofit) 升 baseline 15 → 34: 14 老 followup-* retrofit
# F2 retrofit (本 commit) 升 baseline 34 → 36: 2 mcp-v4-v* 修 (v0.6a/v0.6b/
# v0.6c/v0.6c.1 5 强约束 keyword 加 — 实际 22 fail 中只 2 真正能自动修).
# 20 mcp-v4-v* 仍 fail: 命名 mismatch (mcp-v4-fix-1/pr8/phase-*/momus-*
# 缺 'v' 前缀) + 章节标题 keyword 错位 (v0.4/v0.5a/pr8/pr9 §5-§9 标
# 题不匹配) + §9 缺 (v0.5a/momus-audit/momus-audit-v2). 需手动修.
BASELINE_PASS = 36


def test_check_ship_report_no_regression():
    """F12 教训: NAME_PATTERN 改不破坏老 ship report.

    防 F12-style critical bug: 扩 NAME_PATTERN family (e.g. 加
    followup-*) 暴露老 ship report 不合规, CI 每次 fail.
    """
    repo_root = Path(__file__).parent.parent.parent.parent.parent
    script = repo_root / "scripts" / "check_ship_report.py"
    docs_dir = repo_root / "docs"

    result = subprocess.run(
        ["python3", str(script), str(docs_dir)],
        capture_output=True,
        text=True,
        timeout=30,
    )

    summary_match = re.search(r"摘要[:：]\s*(\d+)\s*pass,\s*(\d+)\s*fail", result.stdout)
    assert summary_match, (
        f"无法解析 check_ship_report.py 输出:\nstdout={result.stdout[:500]}\n"
        f"stderr={result.stderr[:500]}"
    )
    total_pass = int(summary_match.group(1))
    total_fail = int(summary_match.group(2))

    assert total_pass >= BASELINE_PASS, (
        f"ship report pass 数 {total_pass} < baseline {BASELINE_PASS}. "
        f"NAME_PATTERN / 5 强约束 / 9 章节改可能破坏老 ship report. "
        f"当前 fail {total_fail}. "
        f"修法: 1) 撤回检查逻辑改 2) 修老 ship report 3) 升 baseline (新 ship report ship 时手动 +1)"
    )

    print(
        f"✅ ship report pass {total_pass} >= baseline {BASELINE_PASS} "
        f"(fail {total_fail}, 总 {total_pass + total_fail})"
    )
