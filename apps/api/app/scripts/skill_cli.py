"""v0.7.2: Skill admin CLI — per-host pre-shared key 鉴权 + jsonl 审计.

补全 v0.7 工具的真实使用路径 (Momus §0.2 预警).

用法:
  python -m app.scripts.skill_cli list
  python -m app.scripts.skill_cli list enabled
  python -m app.scripts.skill_cli get weather
  python -m app.scripts.skill_cli enable weather
  python -m app.scripts.skill_cli disable web_search

鉴权 (Momus §4.1 决策 2 选项 C):
  - 启用鉴权: 配 SKILL_CLI_REQUIRE_ADMIN=1 + 创建 ~/.skill_admin_key 文件 (per-host pre-shared)
  - 跳过鉴权: 默认 (SKILL_CLI_REQUIRE_ADMIN=0), 假定本地操作者有 admin 权限
  - 提 key 方式: SKILL_CLI_ADMIN_KEY env 或 --admin-key 命令行参数

审计 (Momus §4.2 修正版 6 字段):
  - 文件: .omo/skill_cli_audit.jsonl (gitignored, per-host)
  - 字段: ts / action (enable/disable) / skill_name / user / before (True/False) / after
  - 单进程写 (CLI 本来单进程, 无并发锁)
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


_AUDIT_PATH = Path(__file__).resolve().parents[3] / ".omo" / "skill_cli_audit.jsonl"


def _print(obj) -> None:
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(obj)


def _admin_key_path() -> Path:
    return Path.home() / ".skill_admin_key"


def _require_admin() -> None:
    """Momus §4.1 决策 2 选项 C: 读 ~/.skill_admin_key, 校验输入 key."""
    if os.environ.get("SKILL_CLI_REQUIRE_ADMIN", "0") != "1":
        return  # 鉴权 bypass (默认)

    key_file = _admin_key_path()
    if not key_file.exists():
        sys.exit(
            f"admin key file not found: {key_file}\n"
            f"创建方式: openssl rand -hex 32 > {key_file} && chmod 600 {key_file}\n"
            f"或设 SKILL_CLI_REQUIRE_ADMIN=0 跳过鉴权 (本地 dev)"
        )
    expected = key_file.read_text().strip()

    provided = os.environ.get("SKILL_CLI_ADMIN_KEY")
    if not provided:
        provided = getpass.getpass("admin key: ")
    if not provided or not _constant_time_eq(provided, expected):
        sys.exit("invalid admin key")


def _constant_time_eq(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(
        hashlib.sha256(a.encode()).digest(),
        hashlib.sha256(b.encode()).digest(),
    )


def _audit(action: str, skill_name: str, before: bool | None, after: bool) -> None:
    """Momus §4.2: 6 字段审计, 单进程写 (CLI 本来单进程)."""
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT_PATH.open("a", encoding="utf-8") as f:
            entry = {
                "ts": datetime.now(UTC).isoformat(),
                "action": action,
                "skill_name": skill_name,
                "user": os.environ.get("USER") or getpass.getuser(),
                "before": before,
                "after": after,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 审计写失败不阻塞 CLI 操作


async def cmd_list(args) -> int:
    from app.tools.skill_tool import handle_list_skills

    result = handle_list_skills(filter=args.filter)
    _print(result)
    return 0 if result.get("success") else 1


async def cmd_get(args) -> int:
    from app.tools.skill_tool import handle_get_skill_info

    result = handle_get_skill_info(name=args.name)
    _print(result)
    return 0 if result.get("success") else 1


async def cmd_enable(args) -> int:
    from app.skills._state import is_enabled
    from app.tools.skill_tool import handle_enable_skill

    before = is_enabled(args.name)
    result = handle_enable_skill(name=args.name)
    if result.get("success"):
        _audit("enable", args.name, before=before, after=True)
    _print(result)
    return 0 if result.get("success") else 1


async def cmd_disable(args) -> int:
    from app.skills._state import is_enabled
    from app.tools.skill_tool import handle_disable_skill

    before = is_enabled(args.name)
    result = handle_disable_skill(name=args.name)
    if result.get("success"):
        _audit("disable", args.name, before=before, after=False)
    _print(result)
    return 0 if result.get("success") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill_cli",
        description="v0.7.2: Skill admin CLI (per-host pre-shared key 鉴权 + jsonl 审计)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出 skill")
    p_list.add_argument("--filter", choices=["all", "enabled", "disabled"], default="all")
    p_list.set_defaults(func=cmd_list)

    p_get = sub.add_parser("get", help="查 skill 详情")
    p_get.add_argument("name")
    p_get.set_defaults(func=cmd_get)

    p_enable = sub.add_parser("enable", help="启用 skill")
    p_enable.add_argument("name")
    p_enable.set_defaults(func=cmd_enable)

    p_disable = sub.add_parser("disable", help="禁用 skill")
    p_disable.add_argument("name")
    p_disable.set_defaults(func=cmd_disable)

    return parser


def main() -> int:
    _require_admin()  # Momus §4.1: per-host pre-shared key 鉴权
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
