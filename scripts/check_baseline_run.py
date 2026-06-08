"""G7 防御 check 1/2: 验证 baseline (pytest) 在 ship 前已跑.

防漏跑场景:
- 改 model enum, 没跑 pytest 就 ship, 线上 enum 500 (2026-06-03 事故)
- 改 schema, 没跑 migration test, 漂移上 prod

策略: 检查 .pytest_cache/v/cache/lastfailed 文件 mtime
- mtime < 24h → 视为最近跑过
- mtime >= 24h 或 文件不存在 → 视为未跑 / 太久

用法:
    python scripts/check_baseline_run.py                 # 扫根目录
    python scripts/check_baseline_run.py apps/api         # 指定子目录
    python scripts/check_baseline_run.py --hours 48       # 自定义阈值

返回:
    0 = pytest 在阈值内跑过
    1 = pytest 未跑 或 太久 (ship 前应重跑)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


DEFAULT_HOURS = 24


def find_pytest_caches(root: Path) -> list[Path]:
    """找所有 .pytest_cache/v/cache/lastfailed (每个跑过 pytest 的目录都有)."""
    return sorted(root.rglob(".pytest_cache/v/cache/lastfailed"))


def check_baseline_run(root: Path, hours: int = DEFAULT_HOURS) -> tuple[bool, list[str]]:
    """返回 (pass, errors)."""
    errors: list[str] = []
    threshold_sec = hours * 3600
    now = time.time()

    caches = find_pytest_caches(root)

    if not caches:
        errors.append(
            f"  ✗ 根目录 {root} 下没找到 .pytest_cache — pytest 完全没跑过"
        )
        return False, errors

    for cache in caches:
        project = cache.parent.parent.parent.parent  # .pytest_cache/v/cache/lastfailed → project root
        mtime = cache.stat().st_mtime
        age_hours = (now - mtime) / 3600

        if age_hours > hours:
            errors.append(
                f"  ✗ {project}: pytest 最后跑 {age_hours:.1f}h 前 > {hours}h 阈值"
            )
        else:
            print(f"✅ {project}: pytest {age_hours:.1f}h 前跑过 (≤ {hours}h 阈值)")

    return (len(errors) == 0), errors


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 baseline (pytest) 在 ship 前已跑")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="扫描根目录 (默认: 当前目录)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_HOURS,
        help=f"阈值小时数 (默认: {DEFAULT_HOURS})",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"❌ 路径不存在: {root}")
        return 1

    print(f"=== check_baseline_run: 扫 {root} (阈值 {args.hours}h) ===\n")
    ok, errors = check_baseline_run(root, args.hours)

    if not ok:
        print("\n❌ baseline 漏跑 / 太久:")
        for e in errors:
            print(e)
        print("\n💡 修法: 跑 pytest 后再 ship, 例如:")
        print("   cd apps/api && python -m pytest tests/ --tb=short -q")
        return 1

    print(f"\n=== ✅ baseline 在 {args.hours}h 阈值内跑过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
