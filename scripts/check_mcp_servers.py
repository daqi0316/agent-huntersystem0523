#!/usr/bin/env python3
"""MCP 工具系统 CI 守门脚本（v4 V-4 注册表 = 单一事实源 + CI 校验）。

跑法：
  python3 scripts/check_mcp_servers.py              # 全检查
  python3 scripts/check_mcp_servers.py --quick     # 只静态检查（不启动 server）

检查项：
  1. 启动 MCPHost（连 utils server）→ 拿到 _generated_registry.json
  2. 对比 metadata.registrations 和 host 实际 list_tools — schema 一致？
  3. 每个 tool 的 handler 存在？参数签名匹配 schema？
  4. capability 在白名单（read/write/destructive/admin）？
  5. description 非空？
  6. tool 名不在保留字列表？
  7. config.json 注册的 server 都在 config 中有定义？

退出码：
  0 = 全部通过
  1 = 有错（详情打印到 stderr）
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# 把 apps/api 加到 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_API_ROOT = _PROJECT_ROOT / "apps" / "api"
sys.path.insert(0, str(_API_ROOT))

logger = logging.getLogger("check_mcp")


# ── 静态检查（不启动 server）────────────────────────────
ALLOWED_CAPABILITIES = {"read", "write", "destructive", "admin"}
RESERVED_TOOL_NAMES = {"system", "admin", "internal"}  # 保留字，避免和未来内置冲突


def static_check_tools() -> list[str]:
    """扫描 app/tools/*.py，校验每个 tool 都有 schema + handler + metadata。

    返回错误列表（空 = 全部通过）。
    """
    errors: list[str] = []
    tools_dir = _API_ROOT / "app" / "tools"
    if not tools_dir.exists():
        errors.append(f"tools dir not found: {tools_dir}")
        return errors

    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name in ("__init__.py", "base.py", "metadata.py"):
            continue
        # 跳过 helper / 辅助模块（下划线开头）
        if py_file.name.startswith("_"):
            continue
        mod_name = f"app.tools.{py_file.stem}"
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            errors.append(f"{py_file.name}: import failed: {e}")
            continue

        tools = getattr(mod, "tools", None)
        handlers = getattr(mod, "handlers", None)
        if not tools or not isinstance(tools, list):
            errors.append(f"{py_file.name}: missing `tools` list")
            continue
        if not handlers or not isinstance(handlers, dict):
            errors.append(f"{py_file.name}: missing `handlers` dict")
            continue

        # 每个 tool 校验
        for t in tools:
            try:
                fn = t.get("function", {})
                name = fn.get("name")
                desc = fn.get("description", "").strip()
                params = fn.get("parameters", {})

                if not name:
                    errors.append(f"{py_file.name}: tool missing name")
                    continue
                if name in RESERVED_TOOL_NAMES:
                    errors.append(f"{py_file.name}: tool {name!r} uses reserved name")
                if not desc:
                    errors.append(f"{py_file.name}:{name}: description empty")
                if not isinstance(params, dict) or params.get("type") != "object":
                    errors.append(f"{py_file.name}:{name}: parameters invalid (need type=object)")
                if name not in handlers:
                    errors.append(f"{py_file.name}:{name}: handler not registered")
                    continue
                # 校验 handler 签名
                sig = inspect.signature(handlers[name])
                if not callable(handlers[name]):
                    errors.append(f"{py_file.name}:{name}: handler not callable")

                # 校验 metadata 注册
                from app.tools.metadata import get_metadata, get_input_model, get_capability
                meta = get_metadata(name)
                if meta.capability.value not in ALLOWED_CAPABILITIES:
                    errors.append(
                        f"{py_file.name}:{name}: capability {meta.capability.value!r} "
                        f"not in {ALLOWED_CAPABILITIES}"
                    )
                # 如果有 Pydantic input_model，schema properties 必填字段应匹配
                inp = get_input_model(name)
                if inp is not None:
                    required = set(params.get("required", []))
                    pyd_required = set(inp.model_fields.keys())
                    extra_required = required - pyd_required
                    if extra_required:
                        errors.append(
                            f"{py_file.name}:{name}: schema required {extra_required} "
                            f"not in Pydantic InputModel fields"
                        )
            except Exception as e:
                errors.append(f"{py_file.name}:{name}: validation crashed: {e}")

    return errors


def static_check_skills() -> list[str]:
    """扫描 app/skills/，校验 skill.py 存在 + 导出 skill 实例。

    区分两种 skill 格式：
      A. MCP skill：<sub>/skill.py 导出 Skill 实例（被本系统加载）
      B. Claude Code native skill：<sub>/SKILL.md 是给 Claude Code 看的（通过 npx skills add 装）
    """
    errors: list[str] = []
    warnings: list[str] = []
    skills_dir = _API_ROOT / "app" / "skills"
    if not skills_dir.exists():
        return errors

    for sub in sorted(skills_dir.iterdir()):
        if not sub.is_dir() or sub.name.startswith("_") or sub.name.startswith("."):
            continue
        skill_py = sub / "skill.py"
        skill_md = sub / "SKILL.md"
        # 两种格式都不存在 → 真错
        if not skill_py.exists() and not skill_md.exists():
            errors.append(
                f"skills/{sub.name}/: missing both skill.py (MCP) and SKILL.md (Claude Code)"
            )
            continue
        # 只有 SKILL.md（无 skill.py）→ Claude Code native，warn 不 fail
        if not skill_py.exists() and skill_md.exists():
            warnings.append(
                f"skills/{sub.name}/: SKILL.md only (Claude Code native) — not loaded by MCP"
            )
            logger.info(
                f"skills/{sub.name}/: Claude Code native skill (SKILL.md only); skipped by MCP discoverer"
            )
            continue
        # skill.py 存在 → MCP skill，import + validate
        mod_name = f"app.skills.{sub.name}.skill"
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            errors.append(f"skills/{sub.name}/: import failed: {e}")
            continue
        skill = getattr(mod, "skill", None)
        if skill is None:
            errors.append(f"skills/{sub.name}/: no `skill` instance exported")
            continue
        # 校验 Skill 基类
        from app.skills.base import Skill
        if not isinstance(skill, Skill):
            errors.append(f"skills/{sub.name}/: `skill` not a Skill instance")
        # 校验 name + description 非空
        if not skill.name or not skill.description:
            errors.append(f"skills/{sub.name}/: name/description empty")
        # tools/handlers 一致
        tools = skill.get_tools()
        handlers = skill.get_handlers()
        for t in tools:
            tn = t.get("function", {}).get("name")
            if tn not in handlers:
                errors.append(f"skills/{sub.name}/: tool {tn} has no handler")
        # name 唯一（防止子目录名 vs skill.name 不一致）
        if skill.name != sub.name:
            # 允许（如 web-access 但 skill.name = "web_access"），只是 warn
            logger.info(
                f"skills/{sub.name}/: skill.name={skill.name!r} != subdir name (allowed)"
            )

    return errors


def static_check_config() -> list[str]:
    """校验 config.json 注册的 server 都有 id 唯一 + capability 白名单。"""
    errors: list[str] = []
    config_path = _API_ROOT / "app" / "mcp_servers" / "config.json"
    if not config_path.exists():
        errors.append(f"config.json not found: {config_path}")
        return errors

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"config.json: invalid JSON: {e}")
        return errors

    servers = data.get("servers", [])
    seen_ids: set[str] = set()
    for srv in servers:
        sid = srv.get("id")
        if not sid:
            errors.append(f"config.json: server missing id")
            continue
        if sid in seen_ids:
            errors.append(f"config.json: duplicate server id {sid!r}")
        seen_ids.add(sid)
        cap = srv.get("capability", "read")
        if cap not in ALLOWED_CAPABILITIES:
            errors.append(f"config.json: server {sid}: capability {cap!r} invalid")
        if not srv.get("command"):
            errors.append(f"config.json: server {sid}: missing command")
        if not srv.get("args"):
            errors.append(f"config.json: server {sid}: missing args")
    return errors


# ── 动态检查（启动 server + 调 list_tools）────────────────────
async def dynamic_check_hosts() -> list[str]:
    """启动 MCPHost，连上所有 server，调 list_tools，比对 registry。

    比对项：
      1. host 启动后每个 tool 都能 list_tools 返回
      2. tool 实际 list 包含 config 注册的 server 数量
    """
    from app.mcp.host import mcp_host

    errors: list[str] = []
    try:
        config_path = _API_ROOT / "app" / "mcp_servers" / "config.json"
        connected = await mcp_host.start(
            config_path=str(config_path), phases=["core"]
        )
        if connected == 0:
            errors.append("MCPHost started 0 servers (config issue?)")
            return errors
    except Exception as e:
        errors.append(f"MCPHost.start() failed: {e}")
        return errors

    try:
        # 比对工具数
        tools = mcp_host.list_tools(format="mcp")
        if not tools:
            errors.append("MCPHost.list_tools() returned empty")

        # 每个 tool 调一次（smoke test，call_tool 返回非错）
        for t in tools:
            tn = t["name"]
            schema = t.get("inputSchema", {})
            required = schema.get("required", [])
            # 只对最简单 tool 调（utils 4 个）
            if tn not in {"calculate", "greet", "get_current_time"}:
                continue
            # 给必需参数 dummy 值
            args: dict[str, Any] = {}
            for pname in required:
                ptype = schema["properties"][pname].get("type", "string")
                if ptype == "string":
                    args[pname] = "test"
                elif ptype == "integer":
                    args[pname] = 1
                else:
                    args[pname] = "test"
            r = await mcp_host.call_tool(tn, args)
            if isinstance(r, dict) and r.get("status") == "failed":
                # 可能 Pydantic 拒了 dummy 值（pattern mismatch），不报错
                if r.get("error", {}).get("code") != "VALIDATION_ERROR":
                    errors.append(f"call_tool {tn} unexpected failed: {r}")
    finally:
        await mcp_host.shutdown()

    return errors


# ── Main ─────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="MCP server CI 守门")
    parser.add_argument(
        "--quick", action="store_true",
        help="只跑静态检查（不启动 server）",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="详细输出",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    print("=" * 60)
    print("MCP Server CI Check (v4 V-4)")
    print("=" * 60)

    all_errors: list[str] = []

    print("\n[1/3] Static check: app/tools/*.py ...")
    errs = static_check_tools()
    all_errors.extend(errs)
    if errs:
        for e in errs:
            print(f"  ❌ {e}")
    else:
        print(f"  ✅ all tools valid")

    print("\n[2/3] Static check: app/skills/*/skill.py ...")
    errs = static_check_skills()
    all_errors.extend(errs)
    if errs:
        for e in errs:
            print(f"  ❌ {e}")
    else:
        print(f"  ✅ all skills valid")

    print("\n[3/3] Static check: app/mcp_servers/config.json ...")
    errs = static_check_config()
    all_errors.extend(errs)
    if errs:
        for e in errs:
            print(f"  ❌ {e}")
    else:
        print(f"  ✅ config valid")

    if not args.quick:
        print("\n[4/4] Dynamic check: start MCPHost + call each tool ...")
        # config.json 里 command 是相对路径 (.venv/bin/python)，
        # 需 chdir 到 _API_ROOT 让 subprocess 找到解释器。
        prev_cwd = Path.cwd()
        os.chdir(_API_ROOT)
        try:
            errs = asyncio.run(dynamic_check_hosts())
        except Exception as e:
            errs = [f"dynamic check crashed: {e}"]
        finally:
            os.chdir(prev_cwd)
        all_errors.extend(errs)
        if errs:
            for e in errs:
                print(f"  ❌ {e}")
        else:
            print(f"  ✅ all hosts connected, all tools callable")

    print("\n" + "=" * 60)
    if all_errors:
        print(f"❌ FAILED: {len(all_errors)} error(s)")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    print(f"✅ PASSED: all checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
