"""Tests for BaseAgent integration with layered prompt system (env flag controlled)."""

import os
from unittest.mock import patch

import pytest

from app.agents.base import BaseAgent, ENABLE_LAYERED_PROMPT
from app.agents.prompts import load_prompt, reload_prompts


class _StubAgent(BaseAgent):
    """Concrete BaseAgent for testing prompt loading."""

    async def run(self, input_data: dict) -> dict:
        return self.format_result("completed", {"input": input_data})


def _make_screening_stub() -> _StubAgent:
    agent = _StubAgent(name="screening")
    agent._derive_name = lambda: "screening"
    return agent


def test_enable_layered_prompt_default_false():
    """ENABLE_LAYERED_PROMPT defaults to False (legacy behavior)."""
    assert ENABLE_LAYERED_PROMPT is False


def test_legacy_mode_returns_only_agent_prompt():
    """When ENABLE_LAYERED_PROMPT=false, system_prompt contains only the agent's own .md content."""
    agent = _make_screening_stub()
    prompt = agent.system_prompt
    assert prompt
    assert "Screening Specialist" in prompt
    assert "RecruitAgent" not in prompt
    assert "面试轮次" not in prompt
    assert "脱敏" not in prompt


def test_layered_mode_includes_soul_safety_env():
    """When ENABLE_LAYERED_PROMPT=true, system_prompt includes SOUL + AGENT + SAFETY + ENV."""
    agent = _make_screening_stub()
    with patch("app.agents.base.ENABLE_LAYERED_PROMPT", True):
        prompt = agent.system_prompt
    assert prompt
    assert "Screening Specialist" in prompt
    assert "RecruitAgent" in prompt
    assert "脱敏" in prompt
    assert "环境信息" in prompt
    assert "---" in prompt


def test_env_var_true_enables_layered_mode(monkeypatch):
    """Setting env ENABLE_LAYERED_PROMPT=true flips the constant to True."""
    monkeypatch.setenv("ENABLE_LAYERED_PROMPT", "true")
    import importlib
    import app.agents.base as base_module
    importlib.reload(base_module)
    assert base_module.ENABLE_LAYERED_PROMPT is True
    monkeypatch.setenv("ENABLE_LAYERED_PROMPT", "false")
    importlib.reload(base_module)
    assert base_module.ENABLE_LAYERED_PROMPT is False


def test_legacy_and_layered_produce_different_output():
    """Sanity: the two modes produce different prompts (proves the flag matters)."""
    agent1 = _make_screening_stub()
    legacy = agent1.system_prompt

    agent2 = _make_screening_stub()
    with patch("app.agents.base.ENABLE_LAYERED_PROMPT", True):
        layered = agent2.system_prompt

    assert legacy != layered
    assert len(layered) > len(legacy)
    assert "RecruitAgent" not in legacy
    assert "RecruitAgent" in layered
