"""mcp-skill-mgr server — skill 元操作（PR-9e Type B-light 子进程）。

v0.7: 5 工具 (4 新 + 1 已有), 动态 list_tools 过滤 disabled skill.
  - install_skill_from_url (git clone)
  - list_skills (filter all/enabled/disabled)
  - get_skill_info
  - enable_skill (admin only)
  - disable_skill (admin only)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.tools.skill_tool import handlers as skill_handlers
from app.tools.skill_tool import tools as skill_tools
from app.skills import enabled_tools, enabled_handlers


@entrypoint("mcp-skill-mgr", capability="admin", version="1.0.0")
def main():
    return skill_tools, skill_handlers


@entrypoint("mcp-skill-mgr", capability="admin", version="1.0.0")
def main_enabled():
    """v0.7: 返 enabled skill 的 tool/handler 集合 (动态 list_tools 过滤).

    list_skills / get_skill_info / enable_skill / disable_skill 5 工具**始终**注册
    (来自 skill_tools/skill_handlers), 不受 enable/disable 影响 — 它们管 enable/disable 本身.
    4 skill 子目录 (weather / web_search / web-access / _gallery) 的工具
    按 is_enabled() 过滤, disable 后客户端 list_tools 看不到, 调时 404.
    """
    builtin_tools = list(skill_tools)
    builtin_handlers = dict(skill_handlers)
    extra_tools = enabled_tools()
    extra_handlers = enabled_handlers()
    return builtin_tools + extra_tools, {**builtin_handlers, **extra_handlers}


if __name__ == "__main__":
    main_enabled()
