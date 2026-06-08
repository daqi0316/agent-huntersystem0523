"""G7 防御 check 2/2: 验证 e2e (Playwright) 在 ship 前已跑.

防漏跑场景:
- 改前端 flow, 没跑 playwright e2e 就 ship, 真实登录 500 (2026-06-04 教训)
- 改 B6 (5 关键流程) 模板, 没跑 e2e, 真实后端不通

策略: 检查 apps/web/playwright-report/ 目录 mtime
- mtime < 24h → 视为最近跑过
- mtime >= 24h 或 目录不存在 → 视为未跑 / 太久

用法:
    python scripts/check_e2e_run.py                       # 默认扫 apps/web/playwright-report
    python scripts/check_e2e_run.py --hours 48            # 自定义阈值
    python scripts/check_e2e_run.py path/to/playwright-report  # 自定义路径

返回:
    0 = e2e 在阈值内跑过
    1 = e2e 未跑 或 太久 (ship 前应重跑)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


DEFAULT_HOURS = 24
DEFAULT_REPORT_DIR = "apps/web/playwright-report"


def find_latest_report(report_dir: Path) -> Path | None:
    """找 report 目录里最新生成的文件 (代表最近一次 e2e 跑的时间)."""
    if not report_dir.exists():
        return None
    files = list(report_dir.rglob("*"))
    files = [f for f in files if f.is_file()]
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def check_e2e_run(report_dir: Path, hours: int = DEFAULT_HOURS) -> tuple[bool, list[str]]:
    """返回 (pass, errors)."""
    errors: list[str] = []
    threshold_sec = hours * 3600
    now = time.time()

    if not report_dir.exists():
        errors.append(
            f"  ✗ playwright report 目录不存在: {report_dir} — playwright 完全没跑过"
        )
        return False, errors

    latest = find_latest_report(report_dir)
    if latest is None:
        errors.append(f"  ✗ {report_dir} 是空目录 — playwright 跑过但无输出")
        return False, errors

    mtime = latest.stat().st_mtime
    age_hours = (now - mtime) / 3600

    if age_hours > hours:
        errors.append(
            f"  ✗ {report_dir}: e2e 最后跑 {age_hours:.1f}h 前 > {hours}h 阈值 (最新文件: {latest.name})"
        )
        return False, errors

    print(
        f"✅ {report_dir}: e2e {age_hours:.1f}h 前跑过 (≤ {hours}h 阈值, 最新: {latest.name})"
    )
    return True, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 e2e (Playwright) 在 ship 前已跑")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=DEFAULT_REPORT_DIR,
        help=f"playwright report 目录 (默认: {DEFAULT_REPORT_DIR})",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_HOURS,
        help=f"阈值小时数 (默认: {DEFAULT_HOURS})",
    )
    args = parser.parse_args()

    report_dir = Path(args.report_dir).resolve()
    if report_dir.exists() and not report_dir.is_dir():
        print(f"❌ 不是目录: {report_dir}")
        return 1

    print(f"=== check_e2e_run: 扫 {report_dir} (阈值 {args.hours}h) ===\n")
    ok, errors = check_e2e_run(report_dir, args.hours)

    if not ok:
        print("\n❌ e2e 漏跑 / 太久:")
        for e in errors:
            print(e)
        print("\n💡 修法: 跑 playwright e2e 后再 ship, 例如:")
        print("   cd apps/web && npx playwright test")
        return 1

    print(f"\n=== ✅ e2e 在 {args.hours}h 阈值内跑过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
