"""RouterAgent unit tests — direct class testing with mocks."""

from unittest.mock import AsyncMock

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

    @pytest.mark.asyncio
    async def test_classify_returns_default(self):
        """classify always returns 'default' string."""
        agent = RouterAgent()
        intent = await agent.classify({"text": "anything"})
        assert intent == "default"

    @pytest.mark.asyncio
    async def test_run_returns_stub_for_unknown_intent(self):
        """run returns stub dict when no handler is registered."""
        agent = RouterAgent()
        result = await agent.run({"text": "anything"})
        assert result["agent"] == "router"
        assert result["status"] == "stub"
        assert result["intent"] == "default"

    @pytest.mark.asyncio
    async def test_run_dispatches_to_registered_handler(self):
        """run calls the registered handler's run method."""
        agent = RouterAgent()
        child = _MockAgent("child")
        child.run = AsyncMock(return_value={"agent": "child", "result": "ok"})  # type: ignore[assignment]
        agent.register_route("default", child)

        result = await agent.run({"text": "screen this"})

        child.run.assert_awaited_once_with({"text": "screen this"})
        assert result == {"agent": "child", "result": "ok"}

    @pytest.mark.asyncio
    async def test_run_ignores_unknown_intent(self):
        """run ignores registered intents that don't match classify output."""
        agent = RouterAgent()
        child = _MockAgent("child")
        child.run = AsyncMock()  # type: ignore[assignment]
        agent.register_route("unrelated", child)

        result = await agent.run({"text": "whatever"})

        assert result["status"] == "stub"
        child.run.assert_not_awaited()
