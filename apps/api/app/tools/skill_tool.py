"""Skill management tools for AI recruitment assistant."""
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
