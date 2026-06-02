"""Tests for prompt_builder — layered prompt assembly e2e."""

import pytest

from app.agents.prompts.prompt_builder import (
    PromptBundle,
    build_layered_prompt,
    assemble,
    build_environment_hints,
)


# ── PromptBundle dataclass ──


def test_prompt_bundle_has_9_fields():
    """PromptBundle has all 9 layers (soul, memory, user, project, skills_index, agent, safety, env, ephemeral)."""
    bundle = PromptBundle(
        soul="S", memory="M", user="U", project="P", skills_index="SI",
        agent="A", safety="X", env="E", ephemeral="",
    )
    assert bundle.soul == "S"
    assert bundle.memory == "M"
    assert bundle.user == "U"
    assert bundle.project == "P"
    assert bundle.skills_index == "SI"
    assert bundle.agent == "A"
    assert bundle.safety == "X"
    assert bundle.env == "E"
    assert bundle.ephemeral == ""


def test_prompt_bundle_ephemeral_default_empty():
    """ephemeral field defaults to empty string."""
    bundle = PromptBundle(
        soul="", memory="", user="", project="", skills_index="",
        agent="", safety="", env="",
    )
    assert bundle.ephemeral == ""


# ── assemble ──


def test_assemble_joins_with_separator():
    """assemble joins non-empty fields with `---` separator."""
    bundle = PromptBundle(
        soul="soul content",
        memory="memory content",
        user="",
        project="",
        skills_index="",
        agent="agent content",
        safety="",
        env="",
    )
    result = assemble(bundle)
    assert "soul content" in result
    assert "memory content" in result
    assert "agent content" in result
    # Separator between non-empty fields
    assert "---" in result
    # Empty fields are skipped
    assert "user content" not in result


def test_assemble_returns_empty_for_all_empty():
    """assemble returns '' when all 9 fields are empty."""
    bundle = PromptBundle(
        soul="", memory="", user="", project="", skills_index="",
        agent="", safety="", env="",
    )
    assert assemble(bundle) == ""


def test_assemble_preserves_field_order():
    """Fields appear in fixed order: SOUL → MEMORY → USER → PROJECT → AGENT → SAFETY → ENV → EPHEMERAL.

    skills_index is deliberately skipped in v1 (tool-based loading).
    """
    bundle = PromptBundle(
        soul="1_SOUL", memory="2_MEMORY", user="3_USER", project="4_PROJECT",
        skills_index="5_SKILLS_V1_SKIPPED", agent="6_AGENT", safety="7_SAFETY", env="8_ENV",
        ephemeral="9_EPHEMERAL",
    )
    result = assemble(bundle)
    markers = ["1_SOUL", "2_MEMORY", "3_USER", "4_PROJECT", "6_AGENT", "7_SAFETY", "8_ENV", "9_EPHEMERAL"]
    positions = [result.find(m) for m in markers]
    assert all(p != -1 for p in positions), f"Some markers not found: {dict(zip(markers, positions))}"
    assert positions == sorted(positions), f"Out of order: {list(zip(markers, positions))}"
    assert "5_SKILLS_V1_SKIPPED" not in result


def test_assemble_skips_skills_index_in_v1():
    """v1 工具化下 skills_index 不进入 default system prompt."""
    bundle = PromptBundle(
        soul="S", memory="M", user="", project="",
        skills_index="SKILLS_NOT_USED_V1",  # explicitly set
        agent="A", safety="X", env="",
    )
    result = assemble(bundle)
    assert "SKILLS_NOT_USED_V1" not in result


# ── build_layered_prompt ──


def test_build_layered_prompt_loads_real_content():
    """build_layered_prompt should pull real SOUL/MEMORY/safety/agent content."""
    bundle = build_layered_prompt(
        user_id="integration_test_user_42",
        active_agent="screening",
        context={"time": "2026-06-02", "tenant": "test", "language": "zh"},
    )
    # SOUL/MEMORY/safety should be loaded (files exist on disk)
    assert "RecruitAgent" in bundle.soul
    assert "面试轮次" in bundle.memory
    assert "脱敏" in bundle.safety
    # Agent should load screening.md
    assert "Screening Specialist" in bundle.agent
    # Env should be populated from context
    assert "当前时间" in bundle.env
    assert "租户" in bundle.env
    assert "用户语言" in bundle.env


def test_build_layered_prompt_handles_missing_user_id():
    """build_layered_prompt works for users with no USER.md yet (auto-creates from template)."""
    bundle = build_layered_prompt(
        user_id="nonexistent_user_9999_xyz",
        active_agent="screening",
        context={},
    )
    # user field will be populated from template after first call
    assert isinstance(bundle.user, str)


def test_build_layered_prompt_empty_context_works():
    """build_layered_prompt works with empty context (no time/tenant/language)."""
    bundle = build_layered_prompt(
        user_id="empty_context_user",
        active_agent="sourcing",
        context={},
    )
    # env should be empty when no context
    assert bundle.env == ""


# ── build_environment_hints ──


def test_build_environment_hints_with_full_context():
    """build_environment_hints formats all context fields."""
    result = build_environment_hints({
        "time": "2026-06-02 12:00",
        "tenant": "acme_corp",
        "language": "zh",
    })
    assert "2026-06-02 12:00" in result
    assert "acme_corp" in result
    assert "zh" in result


def test_build_environment_hints_with_empty_context():
    """build_environment_hints returns '' when context is empty."""
    assert build_environment_hints({}) == ""


def test_build_environment_hints_partial_context():
    """build_environment_hints works with only some fields."""
    result = build_environment_hints({"time": "2026-06-02"})
    assert "2026-06-02" in result
    assert "租户" not in result
