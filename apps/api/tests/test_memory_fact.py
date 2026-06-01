"""MemoryFactService unit tests — mock DB at source level."""

from unittest.mock import AsyncMock, Mock, MagicMock

import pytest

from app.services.memory_fact import MemoryFactService as SUT
from app.models.memory_fact import MemoryFact


# ── Fixtures ──


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=Mock(return_value=None),
            scalars=Mock(return_value=Mock(all=Mock(return_value=[]))),
            scalar=Mock(return_value=0),
        )
    )
    db.commit = AsyncMock()
    db.add = Mock()
    return db


@pytest.fixture
def svc(mock_db):
    return SUT(db=mock_db)


def _make_fact(**overrides) -> MemoryFact:
    fields = {
        "id": "f1",
        "user_id": "u1",
        "session_id": "s1",
        "fact_type": "agent_action",
        "subject_type": None,
        "subject_id": None,
        "verb": "searched",
        "object_value": {"query": "Python", "count": 3},
    }
    fields.update(overrides)
    return MemoryFact(**fields)


# ── record_tool_result: unknown tool ──


@pytest.mark.asyncio
async def test_record_unknown_tool(svc):
    facts = await svc.record_tool_result("u1", "s1", "nonexistent_tool", {}, [])
    assert facts == []


# ── Fact builders ──


@pytest.mark.asyncio
async def test_record_search_candidates(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "search_candidates",
        {"query": "Python", "skill": "", "experience_min": 2},
        [{"id": "1", "name": "Zhang"}, {"id": "2", "name": "Li"}],
    )
    assert len(facts) == 1
    assert facts[0].verb == "searched"
    assert facts[0].fact_type == "agent_action"
    assert facts[0].object_value["count"] == 2
    assert facts[0].object_value["query"] == "Python"


@pytest.mark.asyncio
async def test_record_get_candidate(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "get_candidate",
        {"candidate_id": "c1"},
        {"name": "Li Wei", "current_title": "Engineer", "current_company": "TechCo"},
    )
    assert len(facts) == 1
    assert facts[0].verb == "viewed"
    assert facts[0].subject_id == "c1"
    assert facts[0].object_value["name"] == "Li Wei"


@pytest.mark.asyncio
async def test_record_screen_resume_passed(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "screen_resume",
        {"candidate_id": "c1", "job_id": "j1"},
        {"overall_score": 85, "passed": True, "summary": "Good match"},
    )
    assert len(facts) == 2
    verb_map = {f.verb: f for f in facts}
    assert "screened" in verb_map
    assert verb_map["screened"].object_value["score"] == 85
    assert "passed" in verb_map
    assert verb_map["passed"].object_value["job_id"] == "j1"


@pytest.mark.asyncio
async def test_record_screen_resume_failed(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "screen_resume",
        {"candidate_id": "c1", "job_id": "j1"},
        {"overall_score": 45, "passed": False},
    )
    assert len(facts) == 2
    verbs = {f.verb for f in facts}
    assert "failed" in verbs
    assert "screened" in verbs


@pytest.mark.asyncio
async def test_record_schedule_interview(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "schedule_interview",
        {"candidate_id": "c1", "job_id": "j1", "scheduled_time": "2026-06-01T10:00", "notes": "test"},
        {"id": "int1"},
    )
    assert len(facts) == 1
    assert facts[0].verb == "scheduled_interview"
    assert facts[0].object_value["scheduled_time"] == "2026-06-01T10:00"


@pytest.mark.asyncio
async def test_record_generate_jd(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "generate_jd",
        {"title": "Frontend Engineer"},
        {"passed": True},
    )
    assert len(facts) == 1
    assert facts[0].verb == "generated_jd"
    assert facts[0].object_value["title"] == "Frontend Engineer"


@pytest.mark.asyncio
async def test_record_list_jobs(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "list_jobs",
        {"status": "active"},
        [{"id": "j1", "title": "Engineer"}],
    )
    assert len(facts) == 1
    assert facts[0].verb == "listed_jobs"
    assert facts[0].object_value["count"] == 1


@pytest.mark.asyncio
async def test_record_viewed_dashboard(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "get_dashboard_stats", {}, {},
    )
    assert len(facts) == 1
    assert facts[0].verb == "viewed_dashboard"


@pytest.mark.asyncio
async def test_record_search_knowledge(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "search_knowledge",
        {"query": "background check"},
        {"answer": "Do reference calls and verify employment history"},
    )
    assert len(facts) == 1
    assert facts[0].verb == "searched_knowledge"
    assert "background check" in facts[0].object_value["query"]


@pytest.mark.asyncio
async def test_record_get_evaluations(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "get_evaluations",
        {"candidate_id": "c1"},
        [{"id": "e1", "score": 90}],
    )
    assert len(facts) == 1
    assert facts[0].verb == "viewed_evaluations"
    assert facts[0].object_value["count"] == 1


# ── record_tool_result: empty / edge cases ──


@pytest.mark.asyncio
async def test_record_search_empty_result(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "search_candidates",
        {"query": "Rust"},
        [],
    )
    assert len(facts) == 1
    assert facts[0].object_value["count"] == 0


@pytest.mark.asyncio
async def test_record_get_candidate_empty_dict(svc, mock_db):
    facts = await svc.record_tool_result(
        "u1", "s1", "get_candidate",
        {"candidate_id": "c1"},
        {},
    )
    assert len(facts) == 1
    assert facts[0].verb == "viewed"
    assert facts[0].object_value.get("name") == ""


# ── get_structured_context ──


@pytest.mark.asyncio
async def test_context_empty_when_no_facts(svc, mock_db):
    context = await svc.get_structured_context("u1")
    assert context == ""


@pytest.mark.asyncio
async def test_context_with_agent_action(svc, mock_db):
    """Agent-action facts produce a formatted context block."""
    fact = _make_fact(
        id="f1", verb="searched",
        object_value={"query": "Go developers", "count": 5},
    )
    mock_db.execute.return_value.scalars.return_value.all.return_value = [fact]

    context = await svc.get_structured_context("u1")
    assert "【结构化记忆】" in context
    assert "Go developers" in context
    assert "5" in context or "5 人" in context


@pytest.mark.asyncio
async def test_context_with_candidate_facts(svc, mock_db):
    """Candidate-centric facts are grouped by subject."""
    f1 = _make_fact(
        id="f1", fact_type="candidate_action", subject_type="candidate",
        subject_id="c1", verb="viewed",
        object_value={"name": "Zhang San"},
    )
    f2 = _make_fact(
        id="f2", fact_type="decision", subject_type="candidate",
        subject_id="c1", verb="passed",
        object_value={"job_id": "j1", "score": 85},
    )
    mock_db.execute.return_value.scalars.return_value.all.return_value = [f1, f2]

    context = await svc.get_structured_context("u1")
    assert "Zhang San" in context
    assert "已查看" in context
    assert "已通过" in context


@pytest.mark.asyncio
async def test_context_mixed_facts(svc, mock_db):
    """Both candidate and agent-action facts appear in context."""
    f1 = _make_fact(
        id="f1", fact_type="candidate_action", subject_type="candidate",
        subject_id="c1", verb="scheduled_interview",
        object_value={"name": "Li", "scheduled_time": "2026-06-01T10:00"},
    )
    f2 = _make_fact(
        id="f2", verb="generated_jd",
        object_value={"title": "Backend Engineer"},
    )
    mock_db.execute.return_value.scalars.return_value.all.return_value = [f1, f2]

    context = await svc.get_structured_context("u1")
    assert "Li" in context
    assert "Backend Engineer" in context


# ── Private formatting methods ──


class TestFormatting:
    def test_format_fact_viewed(self, svc):
        f = _make_fact(verb="viewed", object_value={"name": "Wang"})
        assert svc._format_fact(f) == "已查看"

    def test_format_fact_screened(self, svc):
        f = _make_fact(verb="screened", object_value={"score": 85})
        assert "已初筛" in svc._format_fact(f)

    def test_format_fact_passed(self, svc):
        f = _make_fact(verb="passed")
        assert svc._format_fact(f) == "已通过初筛"

    def test_format_fact_failed(self, svc):
        f = _make_fact(verb="failed")
        assert svc._format_fact(f) == "未通过初筛"

    def test_format_fact_scheduled(self, svc):
        f = _make_fact(verb="scheduled_interview", object_value={"scheduled_time": "2026-06-01"})
        assert "已安排面试" in svc._format_fact(f)

    def test_format_agent_action_searched(self, svc):
        f = _make_fact(verb="searched", object_value={"query": "React devs", "count": 3})
        assert "React devs" in svc._format_agent_action(f)

    def test_format_agent_action_generated_jd(self, svc):
        f = _make_fact(verb="generated_jd", object_value={"title": "Senior QA"})
        assert "Senior QA" in svc._format_agent_action(f)

    def test_format_agent_action_listed_jobs(self, svc):
        f = _make_fact(verb="listed_jobs", object_value={"count": 5})
        assert "5" in svc._format_agent_action(f)

    def test_format_agent_action_searched_knowledge(self, svc):
        f = _make_fact(verb="searched_knowledge", object_value={"query": "onboarding"})
        assert "onboarding" in svc._format_agent_action(f)

    def test_format_agent_action_viewed_dashboard(self, svc):
        f = _make_fact(verb="viewed_dashboard")
        assert "看板" in svc._format_agent_action(f)

    def test_subject_label_from_name(self, svc):
        f = _make_fact(object_value={"name": "Alice"})
        assert svc._subject_label(f) == "Alice"

    def test_subject_label_fallback_to_id(self, svc):
        f = _make_fact(object_value={}, subject_id="c42")
        assert svc._subject_label(f) == "c42"
