"""test_skill_integration.py — Phase 2 Skills 工具化集成测试。"""

import asyncio
import os
from unittest.mock import patch

import pytest

from app.agents.prompts import list_skills, load_skill
from app.agents.prompts.tool_registry import (
    Tool,
    enable_skills,
    disable_skills,
    is_skills_enabled,
    get_available_tools,
    get_tools_schema,
    call_tool,
    get_skill_names,
    _SKILL_TOOL,
)


class TestSkillFiles:
    """7 个 skill 文件存在且 schema 合法。"""

    def test_all_7_skills_exist(self):
        skills = list_skills()
        assert len(skills) == 7, f"Expected 7 skills, got {len(skills)}: {skills}"

    def test_skill_names_match_expected(self):
        skills = set(list_skills())
        expected = {
            "resume_parser",
            "screening_framework",
            "interview_questions",
            "sourcing_channels",
            "offer_negotiation",
            "onboarding_workflow",
            "recruitment_analytics",
        }
        assert skills == expected, f"Expected {expected}, got {skills}"

    def test_each_skill_loads_non_empty_content(self):
        skills = list_skills()
        for name in skills:
            content = load_skill(name)
            assert content, f"Skill '{name}' returned empty content"
            assert len(content) > 100, f"Skill '{name}' too short ({len(content)} chars)"

    def test_each_skill_has_header(self):
        for name in list_skills():
            content = load_skill(name)
            assert f"# skill: {name}" in content or f"# {name.replace('_', ' ')}" in content.lower()


class TestToolRegistry:
    """tool_registry.py 核心 API 测试。"""

    def test_skills_disabled_by_default(self):
        disable_skills()
        assert is_skills_enabled() is False

    def test_enable_disable_toggle(self):
        disable_skills()
        assert is_skills_enabled() is False
        enable_skills()
        assert is_skills_enabled() is True
        disable_skills()
        assert is_skills_enabled() is False

    def test_get_available_tools_empty_when_disabled(self):
        disable_skills()
        assert get_available_tools() == []
        assert get_tools_schema() == []

    def test_get_available_tools_returns_tool_when_enabled(self):
        enable_skills()
        tools = get_available_tools()
        assert len(tools) == 1
        assert tools[0].name == "load_skill"
        disable_skills()

    def test_get_tools_schema_openai_format(self):
        enable_skills()
        schemas = get_tools_schema("openai")
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "load_skill"
        assert "parameters" in schemas[0]["function"]
        disable_skills()

    def test_get_tools_schema_anthropic_format(self):
        enable_skills()
        schemas = get_tools_schema("anthropic")
        assert len(schemas) == 1
        assert schemas[0]["name"] == "load_skill"
        assert "input_schema" in schemas[0]
        disable_skills()

    def test_get_skill_names_returns_7(self):
        names = get_skill_names()
        assert len(names) == 7
        assert "resume_parser" in names


class TestCallTool:
    """call_tool 异步 handler 测试。"""

    @pytest.mark.asyncio
    async def test_call_tool_valid_skill(self):
        enable_skills()
        result = await call_tool("load_skill", {"name": "resume_parser"})
        assert "【技能：resume_parser】" in result
        assert len(result) > 200
        disable_skills()

    @pytest.mark.asyncio
    async def test_call_tool_all_7_skills(self):
        enable_skills()
        for name in list_skills():
            result = await call_tool("load_skill", {"name": name})
            assert f"【技能：{name}】" in result, f"Skill '{name}' result missing header"
        disable_skills()

    @pytest.mark.asyncio
    async def test_call_tool_nonexistent_returns_error_message(self):
        enable_skills()
        result = await call_tool("load_skill", {"name": "non_existent_skill"})
        assert "不存在" in result
        disable_skills()

    @pytest.mark.asyncio
    async def test_call_tool_disabled_raises(self):
        disable_skills()
        with pytest.raises(ValueError, match="未启用"):
            await call_tool("load_skill", {"name": "resume_parser"})


class TestSkillToolSchema:
    """load_skill 工具的 schema 完整性。"""

    def test_tool_has_required_fields(self):
        schema = _SKILL_TOOL.to_openai_schema()
        func = schema["function"]
        assert func["name"] == "load_skill"
        assert "description" in func
        assert "parameters" in func
        assert func["parameters"]["type"] == "object"
        assert "name" in func["parameters"]["properties"]

    def test_tool_name_enum_matches_skill_list(self):
        schema = _SKILL_TOOL.to_openai_schema()
        enum_values = schema["function"]["parameters"]["properties"]["name"]["enum"]
        assert set(enum_values) == set(list_skills())

    def test_tool_is_required_param(self):
        schema = _SKILL_TOOL.to_openai_schema()
        required = schema["function"]["parameters"].get("required", [])
        assert "name" in required


class TestSkillsEnabledEnvFlag:
    """SKILLS_ENABLED env flag 控制注册行为。"""

    def test_env_flag_false_does_not_register(self, monkeypatch):
        monkeypatch.setenv("SKILLS_ENABLED", "false")
        import importlib
        import app.services.agent_service as agent_svc
        importlib.reload(agent_svc)
        assert agent_svc.SKILLS_ENABLED is False
        tools = agent_svc._get_tools()
        load_skill_tools = [t for t in tools if t.get("function", {}).get("name") == "load_skill"]
        assert len(load_skill_tools) == 0, "load_skill should NOT be in tools when SKILLS_ENABLED=false"

    def test_env_flag_true_registers_load_skill(self, monkeypatch):
        monkeypatch.setenv("SKILLS_ENABLED", "true")
        import importlib
        import app.services.agent_service as agent_svc
        importlib.reload(agent_svc)
        assert agent_svc.SKILLS_ENABLED is True
        tools = agent_svc._get_tools()
        load_skill_tools = [t for t in tools if t.get("function", {}).get("name") == "load_skill"]
        assert len(load_skill_tools) == 1, "load_skill should be in tools when SKILLS_ENABLED=true"
