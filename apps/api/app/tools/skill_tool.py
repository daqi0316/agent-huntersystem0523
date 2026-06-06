"""Skill management tools for AI recruitment assistant.

提供:
  - install_skill_from_url: 从 GitHub URL 装 skill（git clone + 校验 skill.py）
  - install_skill: 从 name/description/tool_name/tool_description/handler_code 装 skill
  - list_skills: 列出已装 skill
  - install_gallery_skill: 从 GitHub URL 或本地路径装 gallery skill
  - list_gallery_skills: 列出已装 gallery skill

PR-1c 注释：这些工具不通过 pkgutil 自动发现（被 agent_service._register_builtins()
显式注册到 _BUILTIN_HANDLERS），但仍需导出 tools 列表以供 _get_tools() 聚合。
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
            # 检查是否有效 skill（需要 skill.py）
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
]

handlers = {
    "install_skill_from_url": handle_install_skill_from_url,
}
