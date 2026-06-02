"""Tests for MemoryFactService — structured memory fact recording and retrieval."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from app.models.memory_fact import MemoryFact
from app.services.memory_fact import (
    MAX_FACTS_PER_INJECTION,
    MemoryFactService,
)


def _mock_fact(
    fact_id: str | None = None,
    user_id: str = "u1",
    session_id: str = "s1",
    fact_type: str = "candidate_action",
    subject_type: str = "candidate",
    subject_id: str = "c1",
    verb: str = "viewed",
    object_value: dict | None = None,
) -> MagicMock:
    f = MagicMock(spec=MemoryFact)
    f.id = fact_id or str(uuid4())
    f.user_id = user_id
    f.session_id = session_id
    f.fact_type = fact_type
    f.subject_type = subject_type
    f.subject_id = subject_id
    f.verb = verb
    f.object_value = object_value or {}
    f.created_at = datetime.now(timezone.utc)
    return f


class TestRecordToolResult:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_empty(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result("u1", "s1", "unknown_tool", {}, {})
        assert result == []

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_empty(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result("u1", "s1", "nonexistent_tool", {}, {})
        assert result == []

    @pytest.mark.asyncio
    async def test_fact_builder_exception_returns_empty(self) -> None:
        """When the fact-builder fn itself raises, the whole thing returns []."""
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        # Pass a type that makes _fact_screen_resume choke on missing keys
        bad_result = "not_a_dict"
        svc._fact_screen_resume = MagicMock(side_effect=RuntimeError("builder error"))
        result = await svc.record_tool_result(
            "u1", "s1", "screen_resume",
            {"candidate_id": "c1", "job_id": "j1"},
            bad_result,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_record_search_candidates(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result(
            "u1", "s1",
            "search_candidates",
            {"query": "python", "skill": "flask"},
            [{"id": "c1", "name": "张三"}],
        )
        assert len(result) == 1
        assert result[0].verb == "searched"
        assert result[0].object_value["query"] == "python"
        assert result[0].object_value["count"] == 1

    @pytest.mark.asyncio
    async def test_record_get_candidate(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result(
            "u1", "s1",
            "get_candidate",
            {"candidate_id": "c1"},
            {"id": "c1", "name": "李四", "current_title": "工程师"},
        )
        assert len(result) == 1
        assert result[0].verb == "viewed"
        assert result[0].subject_id == "c1"

    @pytest.mark.asyncio
    async def test_record_screen_resume(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result(
            "u1", "s1",
            "screen_resume",
            {"candidate_id": "c1", "job_id": "j1"},
            {"overall_score": 85, "passed": True},
        )
        assert len(result) == 2
        verbs = {r.verb for r in result}
        assert "screened" in verbs
        assert "passed" in verbs

    @pytest.mark.asyncio
    async def test_record_schedule_interview(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result(
            "u1", "s1",
            "schedule_interview",
            {"candidate_id": "c1", "scheduled_time": "2025-06-15 14:00"},
            {"id": "interview_1"},
        )
        assert len(result) == 1
        assert result[0].verb == "scheduled_interview"
        assert result[0].object_value["interview_id"] == "interview_1"

    @pytest.mark.asyncio
    async def test_record_list_jobs(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result(
            "u1", "s1",
            "list_jobs",
            {"status": "active"},
            [{"id": "j1"}, {"id": "j2"}],
        )
        assert len(result) == 1
        assert result[0].verb == "listed_jobs"
        assert result[0].object_value["count"] == 2

    @pytest.mark.asyncio
    async def test_record_viewed_dashboard(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result(
            "u1", "s1",
            "get_dashboard_stats",
            {},
            {"total": 10},
        )
        assert len(result) == 1
        assert result[0].verb == "viewed_dashboard"

    @pytest.mark.asyncio
    async def test_record_search_knowledge(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result(
            "u1", "s1",
            "search_knowledge",
            {"query": "如何面试"},
            {"answer": "应该关注候选人的项目经验"},
        )
        assert len(result) == 1
        assert result[0].verb == "searched_knowledge"

    @pytest.mark.asyncio
    async def test_record_get_evaluations(self) -> None:
        db = AsyncMock()
        db.add = Mock()
        svc = MemoryFactService(db)
        result = await svc.record_tool_result(
            "u1", "s1",
            "get_evaluations",
            {"candidate_id": "c1"},
            [{"id": "e1"}, {"id": "e2"}],
        )
        assert len(result) == 1
        assert result[0].verb == "viewed_evaluations"
        assert result[0].object_value["count"] == 2


class TestGetStructuredContext:
    @pytest.mark.asyncio
    async def test_no_facts_returns_empty_string(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=mock_result)

        svc = MemoryFactService(db)
        result = await svc.get_structured_context("u1")
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_formatted_context(self) -> None:
        db = AsyncMock()
        f1 = _mock_fact(
            fact_type="candidate_action",
            subject_type="candidate",
            subject_id="c1",
            verb="viewed",
            object_value={"name": "张三"},
        )
        f2 = _mock_fact(
            fact_type="agent_action",
            subject_type=None,
            subject_id="",
            verb="searched",
            object_value={"query": "python", "count": 3},
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[f1, f2])
        db.execute = AsyncMock(return_value=mock_result)

        svc = MemoryFactService(db)
        result = await svc.get_structured_context("u1")
        assert "张三" in result
        assert "已查看" in result
        assert "python" in result


class TestGroupFacts:
    def test_groups_by_subject(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        facts = [
            _mock_fact(subject_type="candidate", subject_id="c1", verb="viewed"),
            _mock_fact(subject_type="candidate", subject_id="c1", verb="screened"),
            _mock_fact(subject_type="candidate", subject_id="c2", verb="viewed"),
        ]
        groups = svc._group_facts(facts)
        assert len(groups) == 2
        by_key = {(g.subject_type, g.subject_id): g for g in groups}
        c1_group = by_key[("candidate", "c1")]
        assert len(c1_group.facts) == 2

    def test_ignores_facts_without_subject_type(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        facts = [
            _mock_fact(subject_type=None, subject_id=None, verb="viewed_dashboard"),
        ]
        groups = svc._group_facts(facts)
        assert groups == []

    def test_format_agent_action_searched(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(
            fact_type="agent_action",
            verb="searched",
            object_value={"query": "golang", "count": 5},
        )
        result = svc._format_agent_action(fact)
        assert "golang" in result
        assert "5" in result

    def test_format_agent_action_generated_jd(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(
            fact_type="agent_action",
            verb="generated_jd",
            object_value={"title": "高级工程师"},
        )
        result = svc._format_agent_action(fact)
        assert "高级工程师" in result

    def test_format_agent_action_listed_jobs(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(
            fact_type="agent_action",
            verb="listed_jobs",
            object_value={"count": 10},
        )
        result = svc._format_agent_action(fact)
        assert "10" in result

    def test_format_agent_action_viewed_dashboard(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(
            fact_type="agent_action",
            verb="viewed_dashboard",
            object_value={},
        )
        result = svc._format_agent_action(fact)
        assert "看板" in result


class TestSubjectLabel:
    def test_uses_object_value_name(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(object_value={"name": "王五"})
        assert svc._subject_label(fact) == "王五"

    def test_falls_back_to_subject_id(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(subject_id="c99", object_value={})
        assert svc._subject_label(fact) == "c99"


class TestFormatFact:
    def test_viewed(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(verb="viewed")
        assert svc._format_fact(fact) == "已查看"

    def test_screened_with_score(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(verb="screened", object_value={"score": 85})
        assert "已初筛" in svc._format_fact(fact)
        assert "85" in svc._format_fact(fact)

    def test_passed(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(verb="passed")
        assert svc._format_fact(fact) == "已通过初筛"

    def test_failed(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(verb="failed")
        assert svc._format_fact(fact) == "未通过初筛"

    def test_unknown_verb_unchanged(self) -> None:
        db = MagicMock()
        svc = MemoryFactService(db)
        fact = _mock_fact(verb="custom_verb")
        assert svc._format_fact(fact) == "custom_verb"
