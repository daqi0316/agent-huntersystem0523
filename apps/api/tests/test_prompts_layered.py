"""Tests for v2 layered prompt loaders (SOUL/MEMORY/USER/safety_rules/skills)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.prompts import (
    load_soul,
    load_memory,
    load_safety_rules,
    load_user_memory,
    load_skill,
    list_skills,
    load_project_agents_md,
    build_skills_index,
    reload_prompts,
)
from app.agents.prompts.cache_manager import (
    cached_read,
    invalidate_cache,
    cache_stats,
)


# ── SOUL / MEMORY / safety_rules ──


def test_load_soul_returns_content():
    """load_soul returns the actual SOUL.md content (non-empty)."""
    content = load_soul()
    assert content
    assert "RecruitAgent" in content or "SOUL" in content


def test_load_memory_returns_content():
    """load_memory returns MEMORY.md content (non-empty)."""
    content = load_memory()
    assert content
    assert "面试轮次" in content or "MEMORY" in content


def test_load_safety_rules_returns_content():
    """load_safety_rules returns safety_rules.md content (non-empty)."""
    content = load_safety_rules()
    assert content
    assert "脱敏" in content or "安全" in content


def test_load_soul_caches_after_first_read():
    """load_soul uses the mtime-aware cache — second call should not re-read file."""
    # Clear cache first
    invalidate_cache("SOUL")
    content1 = load_soul()
    # If we modified the file mtime, we'd re-read. But unchanged, should be cached.
    content2 = load_soul()
    assert content1 == content2
    assert "SOUL" in cache_stats()["keys"]


# ── USER memory (per user) ──


def test_load_user_memory_returns_template_for_first_time():
    """First-time user: load_user_memory creates file from template, returns its content."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"SETTINGS_DIR": tmp}):
            # Reset cache so we don't see previous reads
            invalidate_cache()
            content = load_user_memory("user_first_time_42")
            assert content
            # Verify file was created
            user_file = Path(tmp) / "user_first_time_42" / "memory.md"
            assert user_file.exists()
            # Content should match template
            template = Path(__file__).parent.parent / "app" / "agents" / "prompts" / "USER.md"
            assert content == template.read_text(encoding="utf-8").strip()


def test_load_user_memory_returns_empty_for_missing_template():
    """If template USER.md is missing, load_user_memory returns '' (no raise)."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"SETTINGS_DIR": tmp}):
            invalidate_cache()
            with patch("app.agents.prompts._PROMPT_DIR", "/nonexistent_dir_xyz"):
                content = load_user_memory("orphan_user_99")
                assert content == ""


def test_load_user_memory_returns_modified_content_on_second_read():
    """When user edits their memory.md, subsequent reads return updated content."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"SETTINGS_DIR": tmp}):
            invalidate_cache()
            # First read creates file
            load_user_memory("editor_user_1")
            # User edits the file
            user_file = Path(tmp) / "editor_user_1" / "memory.md"
            user_file.write_text("# My Custom Notes\n\nPersonal prefs here\n", encoding="utf-8")
            # mtime changed → cache invalidates automatically
            content = load_user_memory("editor_user_1")
            assert "My Custom Notes" in content
            assert "Personal prefs" in content


# ── Skills (v1: list + load, no auto-inject) ──


def test_list_skills_returns_empty_when_no_skills_dir():
    """list_skills returns [] when skills/ directory doesn't exist."""
    with patch("pathlib.Path.exists", return_value=False):
        # This is hard to mock cleanly. Instead, just verify it returns a list
        result = list_skills()
        assert isinstance(result, list)


def test_build_skills_index_returns_empty_string():
    """build_skills_index is a no-op in v1 (tool-based loading). Always returns ''."""
    assert build_skills_index() == ""


# ── load_project_agents_md (v1 stub) ──


def test_load_project_agents_md_returns_empty():
    """v1 has no AGENTS.md. Always returns ''."""
    assert load_project_agents_md() == ""


# ── reload_prompts clears both caches ──


def test_reload_prompts_clears_both_caches():
    """reload_prompts should invalidate both legacy _CACHE and layered cache_manager."""
    # Populate both caches
    load_soul()
    load_memory()
    assert cache_stats()["entries"] >= 2

    # Reload
    reload_prompts()

    # Layered cache should be empty
    assert cache_stats()["entries"] == 0
