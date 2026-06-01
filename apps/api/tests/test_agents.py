"""Agent unit tests — RouterAgent, AggregatorAgent, SingleAgent.

RouterAgent tests cover:
  - Rule-based keyword classification (5 intent types + fallback)
  - LLM-enhanced classification (success + error + invalid response)
  - Empty text edge case

AggregatorAgent tests cover:
  - Parallel evaluation (mocked LLM)
  - Parse failure fallback
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.aggregator import AggregatorAgent
from app.agents.human_loop import HumanLoopAgent
from app.agents.router_agent import RouterAgent
from app.agents.single_agent import SingleAgent

pytestmark = pytest.mark.asyncio


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def llm_patch():
    """Start patch on get_llm_client, yield the mock LLM instance."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock()
    patcher = patch("app.agents.router_agent.get_llm_client", return_value=mock_llm)
    patcher.start()
    yield mock_llm
    patcher.stop()


@pytest.fixture
def agg_llm_patch():
    """Patch get_llm_client for AggregatorAgent (different import path)."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock()
    patcher = patch("app.agents.aggregator.get_llm_client", return_value=mock_llm)
    patcher.start()
    yield mock_llm
    patcher.stop()


# ── RouterAgent: rule-based classification ──────────────────────────────


class TestRouterRuleClassify:
    """Test RouterAgent._rule_classify() with keyword matching."""

    @pytest.fixture
    def router(self):
        return RouterAgent(name="test_router")

    async def test_screening_keywords(self, router):
        """"筛选" → screening intent."""
        intent = await router.classify({"text": "帮我筛选简历", "use_llm": False})
        assert intent == "screening"

    async def test_interview_keywords(self, router):
        """"面试" → interview intent."""
        intent = await router.classify({"text": "安排面试", "use_llm": False})
        assert intent == "interview"

    async def test_jd_generation_keywords(self, router):
        """"JD" → jd_generation intent."""
        intent = await router.classify({"text": "生成JD", "use_llm": False})
        assert intent == "jd_generation"

    async def test_knowledge_query_keywords(self, router):
        """"知识库" → knowledge_query intent."""
        intent = await router.classify({"text": "搜索知识库", "use_llm": False})
        assert intent == "knowledge_query"

    async def test_report_keywords(self, router):
        """"报表" → report intent."""
        intent = await router.classify({"text": "查看报表", "use_llm": False})
        assert intent == "report"

    async def test_chat_fallback(self, router):
        """Unrecognized text → chat intent."""
        intent = await router.classify({"text": "今天天气怎么样", "use_llm": False})
        assert intent == "chat"

    async def test_empty_text(self, router):
        """Empty text → chat intent (edge case)."""
        intent = await router.classify({"text": "", "use_llm": False})
        assert intent == "chat"


# ── RouterAgent: LLM classification ─────────────────────────────────────


class TestRouterLLMClassify:
    """Test RouterAgent._llm_classify() with mocked LLM."""

    @pytest.fixture
    def router(self):
        return RouterAgent(name="test_router")

    async def test_llm_returns_valid_intent(self, router, llm_patch):
        """LLM returns a recognized intent."""
        llm_patch.chat.return_value = '{"intent": "screening"}'
        intent = await router.classify({"text": "some ambiguous text", "use_llm": True})
        assert intent == "screening"

    async def test_llm_returns_intent_in_longer_text(self, router, llm_patch):
        """LLM returns a recognized intent in JSON."""
        llm_patch.chat.return_value = '{"intent": "interview"}'
        intent = await router.classify({"text": "book a meeting", "use_llm": True})
        assert intent == "interview"

    async def test_llm_fallback_on_error(self, router, llm_patch):
        """LLM raises exception → falls back to rule-based classification."""
        llm_patch.chat.side_effect = Exception("LLM unavailable")
        intent = await router.classify({"text": "安排面试", "use_llm": True})
        # Falls back to rule which should match "面试" → interview
        assert intent == "interview"

    async def test_llm_fallback_on_invalid_intent(self, router, llm_patch):
        """LLM returns unrecognized intent → falls back to rules."""
        llm_patch.chat.return_value = '{"intent": "unknown_garbage"}'
        intent = await router.classify({"text": "请帮我初筛简历", "use_llm": True})
        # Falls back to rule → "初筛" is an unambiguous screening keyword
        assert intent == "screening"

    async def test_llm_fallback_on_json_error(self, router, llm_patch):
        """LLM returns non-JSON → falls back to rules."""
        llm_patch.chat.return_value = "some random garbage response"
        intent = await router.classify({"text": "请帮我初筛简历", "use_llm": True})
        assert intent == "screening"

    async def test_llm_fallback_on_empty_text(self, router, llm_patch):
        """Empty text with LLM enabled → chat (empty text shortcut)."""
        llm_patch.chat.return_value = "interview"  # shouldn't be called
        intent = await router.classify({"text": "", "use_llm": True})
        assert intent == "chat"


# ── AggregatorAgent ──────────────────────────────────────────────────────


class TestAggregatorAgent:
    """Test AggregatorAgent parallel evaluation and aggregation."""

    @pytest.fixture
    def aggregator(self):
        return AggregatorAgent(name="test_aggregator")

    async def test_run_returns_expected_structure(self, aggregator, agg_llm_patch):
        """Aggregator.run() returns dimension_results + consensus."""
        agg_llm_patch.chat.side_effect = [
            # First 3 calls = per-dimension evaluations
            '{"dimension": "technical", "overall": 8, "summary": "Good"}',
            '{"dimension": "behavioral", "overall": 7, "summary": "OK"}',
            '{"dimension": "experience", "overall": 9, "summary": "Strong"}',
            # 4th call = consensus aggregation
            '{"final_score": 8, "recommendation": "hire"}',
        ]
        result = await aggregator.run({
            "candidate_info": "John, Python dev, 5 years",
        })

        assert result["agent"] == "test_aggregator"
        assert result["status"] == "completed"
        assert len(result["dimension_results"]) == 3
        assert "consensus" in result
        assert result["total_dimensions"] == 3
        assert result["consensus"]["final_score"] == 8

    async def test_parse_failure_fallback(self, aggregator, agg_llm_patch):
        """When LLM returns unparseable JSON, dimension still included with error."""
        agg_llm_patch.chat.side_effect = [
            '{"dimension": "technical", "overall": 8}',
            "broken json{{{",
            '{"dimension": "experience", "overall": 9}',
            '{"final_score": 7, "recommendation": "consider"}',
        ]
        result = await aggregator.run({
            "candidate_info": "Jane, data scientist",
        })

        assert result["status"] == "completed"
        assert len(result["dimension_results"]) == 3
        # The broken dimension should have error flag
        broken = [d for d in result["dimension_results"] if "error" in d]
        assert len(broken) == 1
        assert broken[0]["error"] == "parse_failed"

    async def test_specified_dimensions(self, aggregator, agg_llm_patch):
        """Only specified dimensions are evaluated."""
        agg_llm_patch.chat.side_effect = [
            '{"dimension": "technical", "overall": 8}',
            '{"dimension": "experience", "overall": 9}',
            '{"final_score": 8.5, "recommendation": "strong_hire"}',
        ]
        result = await aggregator.run({
            "candidate_info": "Alice, PM",
            "dimensions": ["technical", "experience"],
        })

        assert len(result["dimension_results"]) == 2
        dims = [d["dimension"] for d in result["dimension_results"]]
        assert "technical" in dims
        assert "experience" in dims
        assert "behavioral" not in dims


# ── SingleAgent ──────────────────────────────────────────────────────────


class TestSingleAgent:
    """Test SingleAgent basic execution."""

    async def test_run_returns_stub_response(self):
        agent = SingleAgent(name="test_single")
        result = await agent.run({"task": "do something"})
        assert result["agent"] == "test_single"
        assert result["status"] == "stub"
        assert "result" in result


# ── RouterAgent: route registration + run ───────────────────────────────


class TestRouterRoute:
    """Test RouterAgent.register_route() and run()."""

    async def test_register_and_run_route(self):
        """Register a SingleAgent route → run dispatches to it."""
        router = RouterAgent(name="r")
        inner = SingleAgent(name="inner")
        router.register_route("chat", inner)
        result = await router.run({"text": "hello", "use_llm": False})
        assert result["agent"] == "inner"
        assert result["status"] == "stub"

    async def test_run_unregistered_returns_intent(self):
        """No handler for intent → returns intent info."""
        router = RouterAgent(name="r")
        result = await router.run({"text": "筛选简历", "use_llm": False})
        assert result["agent"] == "r"
        assert result["intent"] == "screening"

    async def test_run_with_llm(self, llm_patch):
        """run() uses LLM path when use_llm=True."""
        router = RouterAgent(name="r")
        llm_patch.chat.return_value = '{"intent": "interview"}'
        result = await router.run({"text": "schedule a meeting", "use_llm": True})
        assert result["intent"] == "interview"


# ── AggregatorAgent: worker management ──────────────────────────────────


class TestAggregatorWorkers:
    """Test AggregatorAgent.add_worker()."""

    async def test_add_worker(self):
        agg = AggregatorAgent(name="agg")
        assert agg.workers == []
        worker = SingleAgent(name="w1")
        agg.add_worker(worker)
        assert len(agg.workers) == 1
        assert agg.workers[0].name == "w1"


# ── HumanLoopAgent ──────────────────────────────────────────────────────


class TestHumanLoopAgent:
    """Test HumanLoopAgent proposal lifecycle."""

    @pytest.fixture(autouse=True)
    def _patch_db(self):
        def make_approval(**overrides):
            return MagicMock(
                id="test-approval-id",
                action_type=overrides.get("action_type", "test"),
                proposal=overrides.get("proposal", {}),
                status=MagicMock(value="pending"),
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
            )
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(side_effect=lambda user_id, action_type, proposal, **kw: make_approval(action_type=action_type, proposal=proposal))
        mock_svc.resolve = AsyncMock(return_value=None)
        mock_session = MagicMock()
        mock_session.close = AsyncMock()

        patcher1 = patch("app.agents.human_loop.AsyncSessionLocal", return_value=mock_session)
        patcher2 = patch("app.agents.human_loop.ApprovalService", return_value=mock_svc)
        patcher1.start()
        patcher2.start()
        yield
        patcher1.stop()
        patcher2.stop()

    @pytest.fixture
    def hl_llm_patch(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock()
        patcher = patch("app.agents.human_loop.get_llm_client", return_value=mock_llm)
        patcher.start()
        yield mock_llm
        patcher.stop()

    async def test_create_email_proposal_no_llm(self):
        """create_proposal for send_email doesn't call LLM."""
        from app.agents.human_loop import HumanLoopAgent
        agent = HumanLoopAgent(name="hl")
        result = await agent.create_proposal("test-user", "send_email", {
            "to": "a@b.com", "subject": "Hello", "body": "Body",
        })
        assert result["action_type"] == "send_email"
        assert result["status"] == "pending"
        assert result["proposal"]["to"] == "a@b.com"

    async def test_create_schedule_proposal(self, hl_llm_patch):
        hl_llm_patch.chat.return_value = '{"recommended_slot": "2026-06-01 10:00", "duration_minutes": 60}'
        agent = HumanLoopAgent(name="hl")
        result = await agent.create_proposal("test-user", "schedule_interview", {
            "candidate_name": "John",
            "job_title": "Engineer",
        })
        assert result["action_type"] == "schedule_interview"
        assert result["status"] == "pending"
        assert result["proposal"]["recommended_slot"] == "2026-06-01 10:00"

    async def test_confirm_not_found(self):
        agent = HumanLoopAgent(name="hl")
        result = await agent.confirm("nonexistent", "test-user", approved=True)
        assert "error" in result

    async def test_generate_email_draft_static(self):
        """_generate_email_draft returns structured draft."""
        result = HumanLoopAgent._generate_email_draft({
            "to": "test@example.com",
            "subject": "Interview",
            "body": "Hello",
        })
        assert result["to"] == "test@example.com"
        assert result["subject"] == "Interview"

    async def test_llm_parse_failure_fallback(self, hl_llm_patch):
        hl_llm_patch.chat.return_value = "not json at all"
        agent = HumanLoopAgent(name="hl")
        result = await agent.create_proposal("test-user", "schedule_interview", {
            "candidate_name": "Jane", "job_title": "PM",
        })
        assert "error" in result["proposal"]
