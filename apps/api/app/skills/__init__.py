"""Skill 动态加载系统。

每个子目录是一个独立的 skill，必须包含 skill.py，
其中导出一个 Skill 子类实例（变量名：skill）。

支持的技能自动注册到 agent_service 的工具列表。
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Callable

from app.skills.base import Skill

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent

_discovered: dict[str, Skill] | None = None


def discover_skills() -> dict[str, Skill]:
    """扫描 skills/ 子目录，返回 {skill_name: Skill}。

    包括：
    - app/skills/<name>/skill.py（标准 skill）
    - app/skills/_gallery/<name>/skill.py（Gallery 安装的 skill）
    """
    global _discovered
    if _discovered is not None:
        return _discovered

    _discovered = {}

    # 1. 标准 skill（通过 pkgutil）
    for mod_info in pkgutil.iter_modules([str(SKILLS_DIR)]):
        if mod_info.name in ("__init__", "base"):
            continue

        try:
            mod = importlib.import_module(f"app.skills.{mod_info.name}")
            skill: Skill = getattr(mod, "skill", None)
            if skill is not None and isinstance(skill, Skill):
                _discovered[skill.name] = skill
                logger.info("Loaded skill: %s", skill.name)
            else:
                logger.debug("Skipped %s: no 'skill' instance found", mod_info.name)
        except Exception:
            logger.exception("Failed to load skill module: %s", mod_info.name)

    # 2. Gallery skill（_gallery 目录下的子目录，pkgutil 找不到）
    gallery_dir = SKILLS_DIR / "_gallery"
    if gallery_dir.exists():
        for skill_dir in gallery_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            if skill_dir.name.startswith("__") or skill_dir.name.startswith("."):
                continue
            skill_file = skill_dir / "skill.py"
            if not skill_file.exists():
                continue

            # 尝试导入 app.skills._gallery.<name>
            full_name = f"app.skills._gallery.{skill_dir.name}"
            try:
                mod = importlib.import_module(full_name)
                skill = getattr(mod, "skill", None)
                if skill is not None and isinstance(skill, Skill):
                    _discovered[skill.name] = skill
                    logger.info("Loaded gallery skill: %s", skill.name)
                else:
                    logger.debug("Skipped gallery skill %s: no 'skill' instance", skill_dir.name)
            except Exception:
                logger.exception("Failed to load gallery skill module: %s", skill_dir.name)

    return _discovered


def all_tools() -> list[dict]:
    """合并所有 skill 的 tool schema。"""
    tools = []
    for name, skill in discover_skills().items():
        for t in skill.get_tools():
            tools.append(t)
    return tools


def all_handlers() -> dict[str, Callable]:
    """合并所有 skill 的 handler 映射。"""
    handlers = {}
    for name, skill in discover_skills().items():
        handlers.update(skill.get_handlers())
    return handlers
