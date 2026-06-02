"""System Prompt 加载器。

所有 Prompt 放在 prompts/ 目录下作为独立 .md 文件，
不再硬编码在 Python 类中。

v2 扩展：增加分层 Prompt 加载器（SOUL / MEMORY / USER / SAFETY / SKILLS）。
旧 API（load_prompt / reload_prompts / get_available_prompts）保持完全向后兼容。
"""

from __future__ import annotations

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 旧 API（保持不变，向后兼容）──

_PROMPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """从文件加载 System Prompt。不存在时返回空字符串。

    Args:
        name: Prompt 文件名（不含 .md 后缀）

    Returns:
        Prompt 内容字符串，不存在时返回 ""
    """
    if name in _CACHE:
        return _CACHE[name]

    filepath = os.path.join(_PROMPT_DIR, f"{name}.md")
    if not os.path.exists(filepath):
        logger.warning("System prompt file not found: %s", filepath)
        return ""

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        _CACHE[name] = content
        return content
    except Exception as e:
        logger.warning("Failed to load prompt '%s': %s", name, e)
        return ""


def reload_prompts() -> None:
    """清空旧缓存 + 新分层缓存，下次 load_prompt 会重新读取文件（开发模式热加载）。"""
    _CACHE.clear()
    try:
        from app.agents.prompts.cache_manager import invalidate_cache
        invalidate_cache()
    except ImportError:
        pass
    logger.info("System prompt cache cleared (legacy + layered)")


def get_available_prompts() -> list[str]:
    """列出所有可用的 Prompt 名称（不含 .md 后缀）。"""
    files = []
    for f in os.listdir(_PROMPT_DIR):
        if f.endswith(".md"):
            files.append(f[:-3])
    return sorted(files)


# ── v2 新增：分层 Prompt 加载器（带 mtime 失效）──
# 使用 cache_manager.cached_read 实现"读时检查 mtime，失效则重读"。


def _prompt_path(name: str) -> Path:
    """返回 prompts/{name}.md 的 Path 对象。"""
    return Path(_PROMPT_DIR) / f"{name}.md"


def load_soul() -> str:
    """加载 SOUL.md — 所有 Agent 共享的核心身份。

    Returns:
        SOUL.md 内容，文件不存在返回 ""。
    """
    from app.agents.prompts.cache_manager import cached_read
    return cached_read("SOUL", _prompt_path("SOUL"))


def load_memory() -> str:
    """加载 MEMORY.md — 组织级招聘记忆。

    Returns:
        MEMORY.md 内容，文件不存在返回 ""。
    """
    from app.agents.prompts.cache_manager import cached_read
    return cached_read("MEMORY", _prompt_path("MEMORY"))


def load_safety_rules() -> str:
    """加载 safety_rules.md — 强制安全规则（每次注入）。

    Returns:
        safety_rules.md 内容，文件不存在返回 ""。
    """
    from app.agents.prompts.cache_manager import cached_read
    return cached_read("safety_rules", _prompt_path("safety_rules"))


def load_user_memory(user_id: str) -> str:
    """加载 per-user USER.md 副本。

    位置：runtime/users/{user_id}/memory.md（仓库外，git 忽略）
    模板：当前文件目录下的 USER.md
    首次访问自动从模板复制。

    Args:
        user_id: HR 用户 ID

    Returns:
        USER.md 内容，文件不存在返回 ""（不抛）。
    """
    from app.agents.prompts.cache_manager import cached_read
    settings_dir = os.getenv("SETTINGS_DIR", "./runtime/users")
    user_file = Path(settings_dir) / user_id / "memory.md"
    template_file = _prompt_path("USER")

    # 首次访问：自动从模板复制
    if not user_file.exists() and template_file.exists():
        try:
            user_file.parent.mkdir(parents=True, exist_ok=True)
            user_file.write_text(template_file.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info("Created user memory from template: %s", user_file)
        except OSError as e:
            logger.warning("Failed to create user memory %s: %s", user_file, e)
            return ""

    return cached_read(f"user:{user_id}", user_file)


def load_project_agents_md() -> str:
    """加载项目层 AGENTS.md（v1 留空，Day 5 接入）。

    Returns:
        留空返回 ""。
    """
    return ""


def build_skills_index() -> str:
    """构建 skills/ 索引。

    v1 工具化下不注入到默认 system prompt（LLM 通过 load_skill 工具按需调用）。
    返回空字符串。

    Returns:
        "" (v1 留空)
    """
    return ""


def list_skills() -> list[str]:
    """列出所有可用的 skill 名称（不含 .md 后缀）。

    Returns:
        按字母序排列的 skill 名称列表。
    """
    skills_dir = Path(_PROMPT_DIR) / "skills"
    if not skills_dir.exists():
        return []
    return sorted(f.stem for f in skills_dir.glob("*.md"))


def load_skill(name: str) -> str:
    """加载单个 skill 文件（按需调用）。

    Args:
        name: skill 文件名（不含 .md 后缀）

    Returns:
        skill 内容，文件不存在返回 ""。
    """
    from app.agents.prompts.cache_manager import cached_read
    skill_path = Path(_PROMPT_DIR) / "skills" / f"{name}.md"
    return cached_read(f"skill:{name}", skill_path)
