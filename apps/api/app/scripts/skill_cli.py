"""v0.7.1: Skill admin CLI.

补全 v0.7 工具的真实使用路径 (Momus §0.2 预警). 调用方不必自己写代码调
handle_enable_skill 等 handler, 直接命令行:

  python -m app.scripts.skill_cli list
  python -m app.scripts.skill_cli list enabled
  python -m app.scripts.skill_cli get weather
  python -m app.scripts.skill_cli enable weather
  python -m app.scripts.skill_cli disable web_search

admin 鉴权: 本地 CLI 假定操作者有 admin 权限 (per-host state, 修自己机器).
JWT 鉴权只对 HTTP 入口 (MCP tools / API) 适用, CLI 跳鉴权.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _print(obj) -> None:
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(obj)


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
    from app.tools.skill_tool import handle_enable_skill

    result = handle_enable_skill(name=args.name)
    _print(result)
    return 0 if result.get("success") else 1


async def cmd_disable(args) -> int:
    from app.tools.skill_tool import handle_disable_skill

    result = handle_disable_skill(name=args.name)
    _print(result)
    return 0 if result.get("success") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill_cli",
        description="v0.7.1: Skill admin CLI (list/get/enable/disable)",
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
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
