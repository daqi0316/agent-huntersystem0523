"""Tests for ToolCategory and detect_tool_category (P2-C Stage 7)."""
from __future__ import annotations

from app.tools.metadata import ToolCategory, detect_tool_category


class TestToolCategory:
    def test_all_categories_have_unique_values(self) -> None:
        values = [c.value for c in ToolCategory]
        assert len(values) == len(set(values))

    def test_known_categories(self) -> None:
        assert ToolCategory.SCHEDULE.value == "schedule"
        assert ToolCategory.CANDIDATE.value == "candidate"
        assert ToolCategory.RESUME.value == "resume"
        assert ToolCategory.SEARCH.value == "search"
        assert ToolCategory.MCP.value == "mcp"


class TestDetectToolCategory:
    def test_exact_match(self) -> None:
        assert detect_tool_category("parse_resume") == "resume"
        assert detect_tool_category("web_search") == "search"
        assert detect_tool_category("list_jobs") == "job"

    def test_prefix_match(self) -> None:
        assert detect_tool_category("schedule_interview") == "schedule"
        assert detect_tool_category("schedule_meeting") == "schedule"
        assert detect_tool_category("mcp_some_tool") == "mcp"
        assert detect_tool_category("approve_request") == "approval"

    def test_unknown_returns_unknown(self) -> None:
        assert detect_tool_category("nonexistent_tool") == "unknown"

    def test_case_sensitive(self) -> None:
        """工具名大小写敏感。"""
        assert detect_tool_category("Web_Search") == "unknown"

    def test_candidate_tools(self) -> None:
        assert detect_tool_category("get_candidate") == "candidate"
        assert detect_tool_category("search_candidates") == "candidate"

    def test_system_tools(self) -> None:
        assert detect_tool_category("install_skill") == "system"
        assert detect_tool_category("drop_cache") == "system"
