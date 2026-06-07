"""v0.7 skill_mgr 4 新工具 + state 持久化测试。

覆盖:
  1. list_skills 返全部 + enabled/disabled 状态
  2. list_skills filter=enabled 只返 enabled
  3. list_skills filter=disabled 只返 disabled
  4. get_skill_info 返 metadata
  5. get_skill_info 不存在返 NOT_FOUND
  6. enable_skill 持久化到 state json
  7. disable_skill 持久化到 state json
  8. disable skill 后 enabled_tools / enabled_handlers 不再包含

注: v0.6b WS TestClient 踩坑后, v0.7 测试不通过 TestClient spawn server,
直接调 handler + registry 函数, state 用 tmp_path 隔离。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_state_path(tmp_path, monkeypatch):
    """隔离 state.json 到 tmp_path, 不污染真实 .omo/skill_state.json."""
    state_file = tmp_path / "skill_state.json"
    monkeypatch.setattr("app.skills._state._STATE_PATH", state_file)
    # 清理 _state 模块单例缓存
    return state_file


def test_list_skills_returns_all_skills_with_enabled_status(tmp_state_path):
    """list_skills 返全部 + 每 skill 有 enabled 字段."""
    from app.tools.skill_tool import handle_list_skills

    result = handle_list_skills(filter="all")

    assert result["success"] is True
    assert result["count"] >= 1, "至少应有 1 个 skill (weather 或 web_search 等)"
    assert result["filter"] == "all"
    for skill in result["skills"]:
        assert "name" in skill
        assert "description" in skill
        assert "enabled" in skill
        assert "tools" in skill
        assert isinstance(skill["enabled"], bool)


def test_list_skills_filter_enabled_only(tmp_state_path):
    """filter=enabled 只返 enabled, 默认全部 enabled."""
    from app.tools.skill_tool import handle_list_skills

    result = handle_list_skills(filter="enabled")

    assert result["success"] is True
    assert result["filter"] == "enabled"
    for skill in result["skills"]:
        assert skill["enabled"] is True


def test_list_skills_filter_disabled_only(tmp_state_path):
    """filter=disabled 只返 disabled, 默认 0 个."""
    from app.tools.skill_tool import handle_list_skills

    result = handle_list_skills(filter="disabled")

    assert result["success"] is True
    assert result["filter"] == "disabled"
    assert result["count"] == 0, "默认无 disabled skill"


def test_get_skill_info_returns_metadata(tmp_state_path):
    """get_skill_info 返 name / description / tools / enabled."""
    from app.tools.skill_tool import handle_get_skill_info
    from app.skills import discover_skills

    skill_name = next(iter(discover_skills().keys()))
    result = handle_get_skill_info(name=skill_name)

    assert result["success"] is True
    assert result["name"] == skill_name
    assert "description" in result
    assert "enabled" in result
    assert "tools" in result
    assert isinstance(result["tools"], list)


def test_get_skill_info_nonexistent_returns_NOT_FOUND(tmp_state_path):
    """get_skill_info 不存在 skill 返 NOT_FOUND + available_skills 列表."""
    from app.tools.skill_tool import handle_get_skill_info

    result = handle_get_skill_info(name="nonexistent-skill-xyz")

    assert result["success"] is False
    assert result["code"] == "NOT_FOUND"
    assert "available_skills" in result
    assert isinstance(result["available_skills"], list)


def test_enable_skill_persists_to_state_json(tmp_state_path):
    """enable_skill 写 state.json + reload 后 is_enabled True."""
    from app.tools.skill_tool import handle_enable_skill
    from app.skills import discover_skills
    from app.skills._state import is_enabled

    skill_name = next(iter(discover_skills().keys()))
    # 先 disable
    from app.skills._state import set_enabled
    set_enabled(skill_name, False)
    assert is_enabled(skill_name) is False

    # enable
    result = handle_enable_skill(name=skill_name)
    assert result["success"] is True
    assert result["enabled"] is True

    # state.json 持久化
    assert tmp_state_path.exists()
    persisted = json.loads(tmp_state_path.read_text())
    assert persisted[skill_name]["enabled"] is True
    # is_enabled reload 也对
    assert is_enabled(skill_name) is True


def test_disable_skill_persists_to_state_json(tmp_state_path):
    """disable_skill 写 state.json + reload 后 is_enabled False."""
    from app.tools.skill_tool import handle_disable_skill
    from app.skills import discover_skills
    from app.skills._state import is_enabled

    skill_name = next(iter(discover_skills().keys()))

    result = handle_disable_skill(name=skill_name)
    assert result["success"] is True
    assert result["enabled"] is False

    assert tmp_state_path.exists()
    persisted = json.loads(tmp_state_path.read_text())
    assert persisted[skill_name]["enabled"] is False
    assert is_enabled(skill_name) is False


def test_disable_skill_makes_tools_invisible_in_enabled_tools(tmp_state_path):
    """disable 后 enabled_tools / enabled_handlers 不再包含该 skill 的工具 (registry 端验).

    v0.6b WS TestClient 踩坑后, 此测试不通过 TestClient spawn server,
    直接调 registry 函数验 list_tools 过滤效果.
    """
    from app.tools.skill_tool import handle_disable_skill
    from app.skills import discover_skills, enabled_tools, enabled_handlers
    from app.skills._state import set_enabled

    skill_name = next(iter(discover_skills().keys()))
    skill = discover_skills()[skill_name]
    expected_tool_names = [t["function"]["name"] for t in skill.get_tools()]

    # disable
    set_enabled(skill_name, False)

    # enabled_tools / enabled_handlers 不再包含
    enabled_tool_names = [t["function"]["name"] for t in enabled_tools()]
    enabled_handler_names = list(enabled_handlers().keys())

    for tool_name in expected_tool_names:
        assert tool_name not in enabled_tool_names, (
            f"disable {skill_name} 后 {tool_name} 不应在 enabled_tools 中"
        )
        assert tool_name not in enabled_handler_names, (
            f"disable {skill_name} 后 {tool_name} 不应在 enabled_handlers 中"
        )
