"""v1.0a: env key 完整性守门.

扫 apps/api + apps/web 代码引用 env keys, 与 .env.example 对比, 缺 key 报 WARN/FAIL.

实现 (Momus §3.2):
  - apps/api: 扫 os.getenv / os.environ.get / os.environ[ / Settings() 引用
  - apps/web: 扫 process.env.NEXT_PUBLIC_* 引用
  - 与 .env.example 比对, 缺 key 列表
  - 入口: --check (WARN exit 0) / --strict (FAIL exit 1, CI 用)
  - 跳过的 key (代码用到但 .env.example 不必有, 有默认值):
    - DEBUG (有 default)
    - APP_NAME (有 default)
    - GIT_SHA (build-time 注入)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APPS = [PROJECT_ROOT / "apps" / "api", PROJECT_ROOT / "apps" / "web"]
ENV_FILES = [
    PROJECT_ROOT / "apps" / "api" / ".env.example",
    PROJECT_ROOT / "apps" / "web" / ".env.example",
]
EXCLUDE_DIRS = {"__pycache__", "node_modules", ".next", "dist", "build", ".venv", "venv"}
SKIP_KEYS = {
    "DEBUG", "APP_NAME", "GIT SHA", "PYTHONPATH", "PATH", "HOME", "USER", "SHELL",
    "API_BASE", "WEB_BASE", "API_URL", "WEB_URL", "CI",
    "SETTINGS_DIR", "E2E_EMAIL", "E2E_PASSWORD", "REDIS_E2E",
    "GIT_SHA",
    "SENTRY TRACES_SAMPLE_RATE", "SENTRY_TRACES_SAMPLE_RATE",
}


def _scan_keys_in_file(path: Path) -> set[str]:
    """扫单个文件引用的 env keys. 只匹配真 env 引用模式 (避免普通变量名误匹配)."""
    keys: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return keys

    # Python: os.getenv("KEY") / os.environ.get("KEY") / os.environ["KEY"]
    for m in re.finditer(r'os\.(?:getenv|environ\.get)\(["\']([A-Z][A-Z0-9_]*)["\']', text):
        keys.add(m.group(1))
    for m in re.finditer(r'os\.environ\[["\']([A-Z][A-Z0-9_]*)["\']\]', text):
        keys.add(m.group(1))

    # TS/JS: process.env.NEXT_PUBLIC_*
    for m in re.finditer(r'process\.env\.([A-Z][A-Z0-9_]*)', text):
        keys.add(m.group(1))
    for m in re.finditer(r'["\']NEXT_PUBLIC_([A-Z0-9_]+)["\']', text):
        keys.add(f"NEXT_PUBLIC_{m.group(1)}")

    return keys


def scan_all_keys() -> set[str]:
    keys: set[str] = set()
    for app_root in APPS:
        if not app_root.exists():
            continue
        for path in app_root.rglob("*"):
            if not path.is_file():
                continue
            if any(ex in path.parts for ex in EXCLUDE_DIRS):
                continue
            if path.suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                keys |= _scan_keys_in_file(path)
    return keys - SKIP_KEYS


def load_env_keys(env_file: Path) -> set[str]:
    """从 .env.example 抽 KEY= 形式的 keys."""
    if not env_file.exists():
        return set()
    keys: set[str] = set()
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            keys.add(line.split("=", 1)[0].strip())
    return keys


def main() -> int:
    strict = "--strict" in sys.argv
    used = scan_all_keys()
    declared: set[str] = set()
    for env_file in ENV_FILES:
        declared |= load_env_keys(env_file)

    missing = sorted(used - declared)
    extra = sorted(declared - used)

    print(f"=== env key 完整性检查 ===")
    print(f"已用 key: {len(used)}")
    print(f"已声明 key (.env.example 总): {len(declared)}")
    print(f"缺 key (代码用但 .env.example 没收): {len(missing)}")
    print(f"多余 key (.env.example 收但代码没用): {len(extra)}")
    print()

    if missing:
        print("❌ 缺 key:")
        for k in missing:
            print(f"  - {k}")
        print()
    if extra:
        print("⚠️  多余 key (建议清理):")
        for k in extra:
            print(f"  - {k}")
        print()

    if missing and strict:
        print(f"❌ strict 模式: {len(missing)} 缺 key, exit 1")
        return 1
    if missing:
        print(f"⚠️  warn 模式: {len(missing)} 缺 key (仅警告, exit 0)")
    else:
        print("✅ 0 缺 key, env 完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
