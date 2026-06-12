"""RouterAgent unit tests — direct class testing with mocks."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.router_agent import RouterAgent


class _MockAgent:
    """Concrete agent implementing the BaseAgent interface for testing."""

    def __init__(self, name: str = "mock_agent"):
        self.name = name
        self.run = AsyncMock(return_value={"agent": name, "status": "ok"})


class TestRouterAgent:
    """Direct tests for the RouterAgent class."""

    def test_init_sets_name_and_empty_routes(self):
        """Constructor sets name and initializes empty routes dict."""
        agent = RouterAgent(name="test_router")
        assert agent.name == "test_router"
        assert agent.routes == {}

    def test_register_route_stores_agent_by_intent(self):
        """register_route adds agent to routes dict."""
        agent = RouterAgent()
        child = _MockAgent("child_agent")
        agent.register_route("screening", child)
        assert "screening" in agent.routes
        assert agent.routes["screening"] is child

    def test_register_route_multiple(self):
        """Multiple routes are stored separately."""
        agent = RouterAgent()
        a1 = _MockAgent("a")
        a2 = _MockAgent("b")
        agent.register_route("screening", a1)
        agent.register_route("interview", a2)
        assert len(agent.routes) == 2
        assert agent.routes["screening"] is a1
        assert agent.routes["interview"] is a2

    def test_register_route_overwrites_existing(self):
        """register_route overwrites existing entry for same intent."""
        agent = RouterAgent()
        a1 = _MockAgent("old")
        a2 = _MockAgent("new")
        agent.register_route("x", a1)
        agent.register_route("x", a2)
        assert agent.routes["x"] is a2

    def test_rule_classify_screening(self):
        """_rule_classify returns screening for Chinese keywords."""
        agent = RouterAgent()
        intent, conf = agent._rule_classify("帮我筛选简历")
        assert intent == "screening"
        assert conf > 0

    def test_rule_classify_chat_default(self):
        """_rule_classify returns chat for unrecognized input."""
        agent = RouterAgent()
        intent, conf = agent._rule_classify("今天天气怎么样")
        assert intent == "chat"
        assert conf >= 0  # may be 0.0

    def test_rule_classify_english_keywords(self):
        """_rule_classify matches English keywords."""
        agent = RouterAgent()
        intent, _ = agent._rule_classify("I want to schedule an interview")
        assert intent == "interview"

    @pytest.mark.asyncio
    async def test_classify_empty_text_returns_chat(self):
        """classify returns chat for empty text."""
        agent = RouterAgent()
        intent = await agent.classify({"text": ""})
        assert intent == "chat"

    @pytest.mark.asyncio
    async def test_classify_rule_only(self):
        """classify with use_llm=False uses rule matching."""
        agent = RouterAgent()
        intent = await agent.classify({"text": "筛选简历", "use_llm": False})
        assert intent == "screening"

    @pytest.mark.asyncio
    async def test_classify_llm_success(self):
        """classify uses LLM when available and returns correct intent."""
        agent = RouterAgent()
        agent._llm_json_chat = AsyncMock(return_value={"intent": "screening"})

        intent = await agent.classify({"text": "请帮我查一下张三的简历", "use_llm": True})
        assert intent == "screening"

    @pytest.mark.asyncio
    async def test_classify_llm_fallback_to_rule(self):
        """classify falls back to rule when LLM fails."""
        agent = RouterAgent()
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("LLM unavailable"))
        agent._llm = mock_llm

        intent = await agent.classify({"text": "筛选简历", "use_llm": True})
        assert intent == "screening"

    @pytest.mark.asyncio
    async def test_classify_llm_invalid_response(self):
        """classify falls back to rule when LLM returns invalid intent."""
        agent = RouterAgent()
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="something_unknown")
        agent._llm = mock_llm

        # Falls back to rule since "something_unknown" not in INTENT_TYPES
        intent = await agent.classify({"text": "帮忙写个JD", "use_llm": True})
        assert intent == "jd_generation"

    @pytest.mark.asyncio
    async def test_run_returns_routed_for_unknown_intent(self):
        """run returns routed dict when no handler is registered."""
        agent = RouterAgent()
        result = await agent.run({"text": "写个JD"})
        assert result["agent"] == "router"
        assert result["status"] == "routed"
        assert result["intent"] == "jd_generation"

    @pytest.mark.asyncio
    async def test_run_dispatches_to_registered_handler(self):
        """run calls the registered handler's run method."""
        agent = RouterAgent()
        child = _MockAgent("child")
        child.run = AsyncMock(return_value={"agent": "child", "result": "ok"})
        agent.register_route("screening", child)

        result = await agent.run({"text": "筛选简历"})

        child.run.assert_awaited_once()
        assert result == {"agent": "child", "result": "ok"}

    @pytest.mark.asyncio
    async def test_run_ignores_unrelated_intents(self):
        """run returns routed for intents not matching registered routes."""
        agent = RouterAgent()
        child = _MockAgent("child")
        child.run = AsyncMock()
        agent.register_route("interview", child)

        result = await agent.run({"text": "筛选简历"})

        assert result["status"] == "routed"
        assert result["intent"] == "screening"
        child.run.assert_not_awaited()
