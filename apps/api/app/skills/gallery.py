"""Gallery skill registry — 轻量级 SKILL.md 安装器。

流程：
  1. install_gallery_skill(url/path/content) → 解析 SKILL.md
  2. 生成受限 Python handler（只执行 SKILL.md 里定义的命令）
  3. 注册到内存（_gallery_tools / _gallery_handlers）
  4. 同时保存 SKILL.md 原文到 _gallery/<name>/SKILL.md（持久化）

启动时：
  - 扫描 _gallery/*/SKILL.md
  - 重新解析 + 注册 handler（无需重新下载）
"""

from __future__ import annotations

import logging
import re
import urllib.request
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 全局注册表
_gallery_tools: dict[str, dict] = {}  # name -> tool_schema
_gallery_handlers: dict[str, Callable] = {}  # name -> async function

# 持久化目录
_GALLERY_DIR = Path(__file__).parent.parent / "skills" / "_gallery"
_DANGEROUS_PATTERNS = ["__import__", "os.system", "os.popen", "shutil.rmtree", "eval", "exec("]


class SkillGalleryError(Exception):
    pass


# ── 解析 SKILL.md ────────────────────────────────────────────────


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    lines = content.lstrip("\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise SkillGalleryError("SKILL.md must start with --- frontmatter delimiter")

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise SkillGalleryError("SKILL.md missing closing --- in frontmatter")

    import yaml

    try:
        metadata = yaml.safe_load("\n".join(lines[1:end_idx]))
    except yaml.YAMLError as e:
        raise SkillGalleryError(f"Invalid YAML frontmatter: {e}")

    body = "\n".join(lines[end_idx + 1:])
    return metadata or {}, body


def _extract_actions(body: str) -> list[dict[str, str]]:
    actions = []
    current_action = None
    lines = body.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        action_title_match = re.match(r"^##\s+(?:\d+\.\s+)?(.+)", stripped)
        if action_title_match:
            if current_action is not None:
                actions.append(current_action)
            title = action_title_match.group(1).strip()
            current_action = {"title": title, "gh_cmd": None, "curl_cmd": None}
            i += 1
            continue

        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines):
                if lines[i].strip().startswith("```"):
                    break
                code_lines.append(lines[i])
                i += 1

            code = "\n".join(code_lines).strip()
            if not code or code.startswith("#"):
                i += 1
                continue

            if "gh " in code and current_action is not None:
                gh_lines = [l for l in code.split("\n") if "gh " in l and not l.strip().startswith("#")]
                if gh_lines:
                    current_action["gh_cmd"] = gh_lines[0].strip()
            elif ("curl " in code or "http" in code) and current_action is not None:
                curl_lines = [l for l in code.split("\n") if "curl " in l and not l.strip().startswith("#")]
                if curl_lines:
                    current_action["curl_cmd"] = curl_lines[0].strip()
                elif code.startswith("curl "):
                    current_action["curl_cmd"] = code.split("\n")[0].strip()

            i += 1
            continue

        i += 1

    if current_action is not None:
        actions.append(current_action)

    return [a for a in actions if a.get("gh_cmd") or a.get("curl_cmd")]


def _action_to_tool_name(title: str) -> str:
    words = re.sub(r"[^a-zA-Z0-9 ]", "", title).split()
    if not words:
        return "gallery_action"
    words = [w.lower() for w in words if len(w) > 1][:2]
    return "_".join(words) if words else "gallery_action"


# ── 生成受限 handler 函数 ────────────────────────────────────────


def _generate_handler(action: dict[str, str]) -> tuple[str, str, str]:
    tool_name = _action_to_tool_name(action["title"])
    title = action["title"]
    gh_cmd = action.get("gh_cmd") or ""
    curl_cmd = action.get("curl_cmd") or ""

    lines = []
    lines.append("")
    lines.append(f"async def _{tool_name}(**kwargs) -> dict:")
    lines.append(f'    """Gallery tool: {title}"""')
    lines.append("    import subprocess, json")

    if gh_cmd:
        gh_escaped = gh_cmd.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f"    gh_cmd = \"{gh_escaped}\"")

    if curl_cmd:
        curl_escaped = curl_cmd.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f"    curl_cmd = \"{curl_escaped}\"")

    lines.append("    errors = []")

    if gh_cmd:
        lines.append("    if gh_cmd:")
        lines.append("        try:")
        lines.append("            result = subprocess.run(")
        lines.append("                [\"bash\", \"-c\", gh_cmd],")
        lines.append("                capture_output=True, text=True, timeout=30")
        lines.append("            )")
        lines.append("            if result.returncode == 0:")
        lines.append("                try:")
        lines.append("                    return {\"result\": json.loads(result.stdout)}")
        lines.append("                except json.JSONDecodeError:")
        lines.append("                    return {\"result\": result.stdout}")
        lines.append("            else:")
        lines.append("                errors.append(result.stderr or \"gh failed\")")
        lines.append("        except FileNotFoundError:")
        lines.append("            errors.append(\"gh not found\")")
        lines.append("        except Exception as e:")
        lines.append("            errors.append(str(e))")

    if curl_cmd:
        lines.append("    if curl_cmd:")
        lines.append("        try:")
        lines.append("            result = subprocess.run(")
        lines.append("                [\"bash\", \"-c\", curl_cmd],")
        lines.append("                capture_output=True, text=True, timeout=30")
        lines.append("            )")
        lines.append("            if result.returncode == 0:")
        lines.append("                try:")
        lines.append("                    return {\"result\": json.loads(result.stdout)}")
        lines.append("                except json.JSONDecodeError:")
        lines.append("                    return {\"result\": result.stdout}")
        lines.append("            else:")
        lines.append("                errors.append(result.stderr or \"curl failed\")")
        lines.append("        except Exception as e:")
        lines.append("            errors.append(str(e))")

    lines.append("    if errors:")
    lines.append("        return {\"error\": \"; \".join(errors)}")
    lines.append("    return {\"error\": \"No valid command available (gh/curl)\"}")

    return tool_name, "\n".join(lines), title


def _validate_handler_code(code: str) -> list[str]:
    """验证生成的 handler 代码安全性。"""
    issues = []
    for pat in _DANGEROUS_PATTERNS:
        if pat in code:
            issues.append(f"危险模式: {pat}")
    return issues


# ── 启动恢复 ──────────────────────────────────────────────────────


def _restore_from_disk() -> int:
    """扫描 _gallery/*/SKILL.md，重新注册到内存。返回恢复数量。"""
    if not _GALLERY_DIR.exists():
        return 0

    restored = 0
    for skill_dir in _GALLERY_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("__") or skill_dir.name.startswith("."):
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            content = skill_md.read_text(encoding="utf-8")
            result = _register_skill_content(content, source=f"磁盘恢复: {skill_dir.name}")
            if result.get("success"):
                restored += 1
                logger.info("Restored gallery skill from disk: %s", skill_dir.name)
            else:
                logger.warning("Failed to restore %s: %s", skill_dir.name, result.get("error"))
        except Exception as e:
            logger.warning("Error restoring skill from %s: %s", skill_dir, e)

    return restored


def _register_skill_content(content: str, source: str = "unknown") -> dict:
    """解析 SKILL.md 内容并注册到内存（不写文件）。"""
    try:
        metadata, body = _parse_frontmatter(content)
    except SkillGalleryError as e:
        return {"success": False, "error": f"解析失败 [{source}]: {e}"}

    skill_name = metadata.get("name", "")
    if not skill_name:
        return {"success": False, "error": f"SKILL.md 缺少 name 字段 [{source}]"}

    description = metadata.get("description", "")
    actions = _extract_actions(body)
    if not actions:
        return {"success": False, "error": f"未找到有效的操作 [{source}]"}

    registered_tools = []
    for action in actions:
        tool_name, handler_code, title = _generate_handler(action)

        issues = _validate_handler_code(handler_code)
        if issues:
            return {"success": False, "error": f"代码验证失败 [{source}]: " + "; ".join(issues)}

        global_namespace = {}
        exec(handler_code, global_namespace)

        handler_fn = global_namespace.get(f"_{tool_name}")
        if not handler_fn:
            return {"success": False, "error": f"生成 handler 失败 [{source}]"}

        _gallery_tools[tool_name] = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": f"执行 GitHub 操作: {title}",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
        _gallery_handlers[tool_name] = handler_fn
        registered_tools.append(tool_name)
        logger.info("Gallery registered tool: %s (from %s)", tool_name, source)

    return {
        "success": True,
        "name": skill_name,
        "description": description,
        "tools": registered_tools,
        "source": source,
    }


# ── 启动时恢复 ────────────────────────────────────────────────────

# 进程启动时恢复（模块首次导入时自动执行）
_restored_count = _restore_from_disk()
if _restored_count > 0:
    logger.info("Gallery: restored %d skills from disk", _restored_count)


# ── Public API ──────────────────────────────────────────────────


async def install_gallery_skill_from_url(url: str) -> dict:
    """从 GitHub URL 安装 SKILL.md。"""
    url = url.rstrip("/")

    if "/raw/" in url:
        raw_url = url
    elif "/blob/" in url:
        raw_url = url.replace("/blob/", "/raw/")
    else:
        parts = url.rstrip("/").split("/")
        if len(parts) < 2:
            return {"success": False, "error": f"Invalid GitHub URL: {url}"}
        owner, repo = parts[-2], parts[-1]
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/skills/github/github-issues/SKILL.md"

    try:
        with urllib.request.urlopen(raw_url, timeout=30) as resp:
            content = resp.read().decode("utf-8")
    except Exception as e:
        return {"success": False, "error": f"下载失败: {e}"}

    return await install_gallery_skill_from_content(content, source=f"GitHub: {url}")


async def install_gallery_skill_from_path(path: str) -> dict:
    """从本地文件安装 SKILL.md。"""
    p = Path(path)
    if not p.exists():
        return {"success": False, "error": f"文件不存在: {path}"}
    if not p.is_file():
        return {"success": False, "error": f"不是文件: {path}"}

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return {"success": False, "error": f"读取失败: {e}"}

    return await install_gallery_skill_from_content(content, source=f"本地文件: {p.absolute()}")


async def install_gallery_skill_from_content(content: str, source: str = "unknown") -> dict:
    """安装 SKILL.md：解析 → 注册内存 → 持久化到磁盘。"""
    # 1. 解析
    try:
        metadata, body = _parse_frontmatter(content)
    except SkillGalleryError as e:
        return {"success": False, "error": f"解析失败 [{source}]: {e}"}

    skill_name = metadata.get("name", "")
    if not skill_name:
        return {"success": False, "error": f"SKILL.md 缺少 name 字段 [{source}]"}

    description = metadata.get("description", "")
    actions = _extract_actions(body)
    if not actions:
        return {"success": False, "error": f"未找到有效的 GitHub 操作 [{source}]"}

    # 2. 注册到内存
    registered_tools = []
    for action in actions:
        tool_name, handler_code, title = _generate_handler(action)

        issues = _validate_handler_code(handler_code)
        if issues:
            return {"success": False, "error": f"代码验证失败 [{source}]: " + "; ".join(issues)}

        global_namespace = {}
        exec(handler_code, global_namespace)

        handler_fn = global_namespace.get(f"_{tool_name}")
        if not handler_fn:
            return {"success": False, "error": f"生成 handler 失败 [{source}]"}

        _gallery_tools[tool_name] = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": f"执行 GitHub 操作: {title}",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
        _gallery_handlers[tool_name] = handler_fn
        registered_tools.append(tool_name)
        logger.info("Gallery registered tool: %s (from %s)", tool_name, source)

    # 3. 持久化到磁盘（SKILL.md 原文）
    safe_name = skill_name.replace("-", "_").replace(" ", "_")
    skill_dir = _GALLERY_DIR / safe_name
    try:
        _GALLERY_DIR.mkdir(parents=True, exist_ok=True)
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        logger.info("Gallery persisted SKILL.md to %s", skill_dir / "SKILL.md")
    except Exception as e:
        logger.warning("Failed to persist SKILL.md: %s", e)
        # 持久化失败不影响内存注册

    tool_names = [_action_to_tool_name(a["title"]) for a in actions]
    return {
        "success": True,
        "name": skill_name,
        "description": description,
        "tools": tool_names,
        "path": f"app/skills/_gallery/{safe_name}/",
        "source": source,
    }


def list_gallery_skills() -> list[dict]:
    """返回所有已注册的 gallery skill。"""
    return [
        {"name": name, "schema": schema}
        for name, schema in _gallery_tools.items()
    ]


def get_gallery_tools() -> list[dict]:
    """返回所有 gallery tool schema（供 LLM 调用）。"""
    return list(_gallery_tools.values())


def get_gallery_handlers() -> dict[str, Callable]:
    """返回所有 gallery handler（供工具调用分发）。"""
    return dict(_gallery_handlers)
