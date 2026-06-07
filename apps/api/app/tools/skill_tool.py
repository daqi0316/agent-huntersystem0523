"""Skill management tools for AI recruitment assistant.

v0.7: 5 工具 (1 已有 + 4 新):
  - install_skill_from_url: 从 GitHub URL 装 skill (git clone)
  - list_skills: 列已装 skill (含 enabled/disabled 状态)
  - get_skill_info: 查 skill 详情 (name / description / tools / enabled)
  - enable_skill: 启用 skill (admin only)
  - disable_skill: 禁用 skill (admin only, runtime_tools 不杀进程, 只下次 spawn 不返回)

PR-1c 注释：install_skill_from_url 不通过 pkgutil 自动发现（被 agent_service._register_builtins()
显式注册到 _BUILTIN_HANDLERS），但仍需导出 tools 列表以供 _get_tools() 聚合。
v0.7 新 4 工具通过 _get_handlers() 动态返回 (registry enabled_skills 过滤)。
"""
import subprocess
from pathlib import Path

SKILLS_INSTALL_BASE = Path(__file__).parent.parent / "skills"


def handle_install_skill_from_url(url: str) -> dict:
    if not url:
        return {"success": False, "result": "URL is required"}

    parts = url.rstrip("/").split("/")
    if len(parts) < 2:
        return {"success": False, "result": f"Invalid GitHub URL: {url}"}

    repo_name = parts[-1]
    target_dir = SKILLS_INSTALL_BASE / repo_name

    if target_dir.exists():
        return {"success": False, "result": f"Skill 已存在: {repo_name}（路径: app/skills/{repo_name}/）"}

    try:
        result = subprocess.run(
            ["git", "clone", url, str(target_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            has_skill_py = (target_dir / "skill.py").exists()
            status = "有效 skill，已启用" if has_skill_py else "已克隆，但缺少 skill.py，需手动编写"
            return {
                "success": True,
                "result": f"安装成功\n路径: app/skills/{repo_name}/\n状态: {status}",
                "path": str(target_dir),
                "has_skill_py": has_skill_py,
            }
        else:
            error = result.stderr[-500:] if result.stderr else "Unknown error"
            return {"success": False, "result": f"git clone 失败:\n{error}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "result": "安装超时（2分钟），可能网络较慢"}
    except FileNotFoundError:
        return {"success": False, "result": "未找到 git 命令"}
    except Exception as e:
        return {"success": False, "result": f"安装异常: {str(e)}"}


def handle_list_skills(filter: str = "all") -> dict:
    """v0.7: 列出已装 skill + enabled 状态."""
    from app.skills import discover_skills
    from app.skills._state import is_enabled

    state_filter = filter if filter in ("all", "enabled", "disabled") else "all"
    items = []
    for name, skill in discover_skills().items():
        enabled = is_enabled(name)
        if state_filter == "enabled" and not enabled:
            continue
        if state_filter == "disabled" and enabled:
            continue
        items.append({
            "name": name,
            "description": skill.description,
            "enabled": enabled,
            "tools": [t["function"]["name"] for t in skill.get_tools()],
        })
    return {"success": True, "skills": items, "count": len(items), "filter": state_filter}


def handle_get_skill_info(name: str) -> dict:
    """v0.7: 查 skill 详情."""
    from app.skills import discover_skills
    from app.skills._state import is_enabled

    if not name:
        return {"success": False, "error": "name is required", "code": "INVALID_INPUT"}

    skills = discover_skills()
    skill = skills.get(name)
    if skill is None:
        return {
            "success": False,
            "error": f"Skill not found: {name}",
            "code": "NOT_FOUND",
            "available_skills": list(skills.keys()),
        }
    return {
        "success": True,
        "name": name,
        "description": skill.description,
        "enabled": is_enabled(name),
        "tools": [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
            }
            for t in skill.get_tools()
        ],
    }


def handle_enable_skill(name: str) -> dict:
    """v0.7: 启用 skill (admin only via metadata.py)."""
    from app.skills import discover_skills
    from app.skills._state import set_enabled

    if not name:
        return {"success": False, "error": "name is required", "code": "INVALID_INPUT"}
    if name not in discover_skills():
        return {"success": False, "error": f"Skill not found: {name}", "code": "NOT_FOUND"}

    set_enabled(name, True)
    return {"success": True, "name": name, "enabled": True}


def handle_disable_skill(name: str) -> dict:
    """v0.7: 禁用 skill (admin only via metadata.py)."""
    from app.skills import discover_skills
    from app.skills._state import set_enabled

    if not name:
        return {"success": False, "error": "name is required", "code": "INVALID_INPUT"}
    if name not in discover_skills():
        return {"success": False, "error": f"Skill not found: {name}", "code": "NOT_FOUND"}

    set_enabled(name, False)
    return {"success": True, "name": name, "enabled": False}


# ── Tools（PR-5 补：原本只有 handler，CI 守门要求 tools 列表）──
tools = [
    {
        "type": "function",
        "function": {
            "name": "install_skill_from_url",
            "description": (
                "从 GitHub URL 克隆一个 skill 仓库到 app/skills/ 目录。"
                "clone 完后会检查是否存在 skill.py；存在则视为有效 skill。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "GitHub 仓库 URL，如 https://github.com/eze-is/web-access",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "列出已装 skill 及 enable/disable 状态。filter=all|enabled|disabled。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["all", "enabled", "disabled"],
                        "description": "过滤维度: all=全部, enabled=仅启用, disabled=仅禁用",
                        "default": "all",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill_info",
            "description": "查 skill 详情 (name / description / tools / enabled 状态)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "skill 名称 (skill.name 属性)",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enable_skill",
            "description": "启用 skill (admin only)。修改 .omo/skill_state.json, 下次 spawn mcp-skill-mgr 生效。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "skill 名称",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "disable_skill",
            "description": "禁用 skill (admin only)。runtime 不杀进程, 只下次 spawn mcp-skill-mgr 工具列表不再返回。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "skill 名称",
                    },
                },
                "required": ["name"],
            },
        },
    },
]

handlers = {
    "install_skill_from_url": handle_install_skill_from_url,
    "list_skills": handle_list_skills,
    "get_skill_info": handle_get_skill_info,
    "enable_skill": handle_enable_skill,
    "disable_skill": handle_disable_skill,
}
