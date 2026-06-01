"""Tests for app/agents/bootstrap.py — Agent initialization and routing."""

from unittest.mock import patch

import pytest

from app.agents.registry import AgentRegistry
from app.agents.router_agent import RouterAgent


@pytest.fixture(autouse=True)
def reset_registry():
    AgentRegistry.clear()
    from app.agents.bootstrap import reset_for_testing
    reset_for_testing()
    yield
    AgentRegistry.clear()
    from app.agents.bootstrap import reset_for_testing
    reset_for_testing()


class TestInitAgents:
    def test_init_creates_specialist_agents(self):
        from app.agents.bootstrap import init_agents

        router = init_agents()
        assert router is not None
        assert isinstance(router, RouterAgent)

        # Verify all specialist agents are in the registry
        for name in ("screening", "interview", "sourcing", "offering", "onboarding", "analytics"):
            agent = AgentRegistry.resolve(name)
            assert agent is not None, f"{name} should be registered"

    def test_init_registers_routes(self):
        from app.agents.bootstrap import init_agents

        router = init_agents()

        # Verify routes are populated
        expected_intents = {
            "screening", "interview", "jd_generation", "candidate_search",
            "outreach", "channel_strategy", "offering", "onboarding",
            "analytics", "report",
        }
        assert expected_intents.issubset(router.routes.keys())

    def test_init_is_idempotent(self):
        from app.agents.bootstrap import init_agents

        router1 = init_agents()
        router2 = init_agents()

        # Second call should return the same instance
        assert router1 is router2

    def test_get_router_before_init(self):
        from app.agents.bootstrap import get_router

        router = get_router()
        assert router is not None
        assert isinstance(router, RouterAgent)


class TestRouterRouting:
    def test_screening_route_resolves(self):
        from app.agents.bootstrap import init_agents
        from app.agents.screening_agent import ScreeningAgent

        router = init_agents()
        handler = router.routes.get("screening")
        assert handler is not None
        assert isinstance(handler, ScreeningAgent)

    def test_interview_route_resolves(self):
        from app.agents.bootstrap import init_agents
        from app.agents.interview_agent import InterviewAgent

        router = init_agents()
        handler = router.routes.get("interview")
        assert handler is not None
        assert isinstance(handler, InterviewAgent)

    def test_sourcing_route_resolves(self):
        from app.agents.bootstrap import init_agents
        from app.agents.sourcing_agent import SourcingAgent

        router = init_agents()
        for intent in ("jd_generation", "candidate_search", "outreach", "channel_strategy"):
            handler = router.routes.get(intent)
            assert handler is not None, f"Route '{intent}' should exist"
            assert isinstance(handler, SourcingAgent), f"Route '{intent}' should map to SourcingAgent"

    def test_offering_route_resolves(self):
        from app.agents.bootstrap import init_agents
        from app.agents.offering_agent import OfferingAgent

        router = init_agents()
        handler = router.routes.get("offering")
        assert handler is not None
        assert isinstance(handler, OfferingAgent)

    def test_onboarding_route_resolves(self):
        from app.agents.bootstrap import init_agents
        from app.agents.onboarding_agent import OnboardingAgent

        router = init_agents()
        handler = router.routes.get("onboarding")
        assert handler is not None
        assert isinstance(handler, OnboardingAgent)

    def test_analytics_route_resolves(self):
        from app.agents.bootstrap import init_agents
        from app.agents.analytics_agent import AnalyticsAgent

        router = init_agents()
        for intent in ("analytics", "report"):
            handler = router.routes.get(intent)
            assert handler is not None, f"Route '{intent}' should exist"
            assert isinstance(handler, AnalyticsAgent)


class TestRouterDispatch:
    @pytest.mark.asyncio
    async def test_router_classifies_and_dispatches_screening(self):
        from app.agents.bootstrap import init_agents
        from app.agents.screening_agent import ScreeningAgent

        router = init_agents()
        with patch.object(ScreeningAgent, "run", return_value={"agent": "screening", "status": "completed", "result": {"overall_score": 85}}):
            result = await router.run({"text": "筛选简历", "use_llm": False})
        assert result.get("agent") == "screening"
        assert result.get("status") == "completed"

    @pytest.mark.asyncio
    async def test_router_classifies_and_dispatches_interview(self):
        from app.agents.bootstrap import init_agents
        from app.agents.interview_agent import InterviewAgent

        router = init_agents()
        with patch.object(InterviewAgent, "run", return_value={"agent": "interview", "status": "completed", "result": {"plan": []}}):
            result = await router.run({"text": "安排面试", "use_llm": False})
        assert result.get("agent") == "interview"
        assert result.get("status") == "completed"

    @pytest.mark.asyncio
    async def test_router_classifies_and_dispatches_offering(self):
        from app.agents.bootstrap import init_agents
        from app.agents.offering_agent import OfferingAgent

        router = init_agents()
        with patch.object(OfferingAgent, "run", return_value={"agent": "offering", "status": "completed", "result": {"total_package": 405000}}):
            result = await router.run({"text": "发offer", "use_llm": False})
        assert result.get("agent") == "offering"
        assert result.get("status") == "completed"

    @pytest.mark.asyncio
    async def test_router_classifies_and_dispatches_onboarding(self):
        from app.agents.bootstrap import init_agents
        from app.agents.onboarding_agent import OnboardingAgent

        router = init_agents()
        with patch.object(OnboardingAgent, "run", return_value={"agent": "onboarding", "status": "completed", "result": {"onboarding_plan": {"milestones": []}}}):
            result = await router.run({"text": "生成入职计划", "use_llm": False})
        assert result.get("agent") == "onboarding"
        assert result.get("status") == "completed"

    @pytest.mark.asyncio
    async def test_router_classifies_chat_as_fallback(self):
        from app.agents.bootstrap import init_agents

        router = init_agents()
        result = await router.run({"text": "你好", "use_llm": False})
        assert result.get("intent") == "chat"

    @pytest.mark.asyncio
    async def test_router_fallback_no_handler(self):
        from app.agents.bootstrap import init_agents

        router = init_agents()
        result = await router.run({"text": "这是个未知意图测试", "use_llm": False})
        assert result.get("intent") in ("chat", "settings")


class TestFormatAgentResult:
    @pytest.mark.parametrize("intent,result_dict,expected_substring", [
        ("screening", {"result": {"overall_score": 85, "gate_passed": True}}, "85"),
        ("screening", {"result": {"overall_score": 40, "gate_passed": False}}, "40"),
        ("interview", {"result": {"plan": [{"round": "R1", "label": "技术面"}, {"round": "R2", "label": "HR面"}]}}, "R1"),
        ("offering", {"result": {"total_package": 405000}}, "405,000"),
        ("onboarding", {"result": {"onboarding_plan": {"milestones": [{"id": "M1"}, {"id": "M2"}]}}}, "2"),
        ("analytics", {"result": {"funnel": {"applied": 100, "screened": 60}}}, "100"),
        ("sourcing", {"result": {"talent_map": [{"company": "字节跳动"}], "total_targets": 1}}, "1"),
        ("sourcing", {"result": {"recommendations": [], "total_budget": 50000}}, "50,000"),
    ])
    def test_format_agent_result(self, intent, result_dict, expected_substring):
        from app.services.agent_service import _format_agent_result

        result = _format_agent_result(intent, result_dict)
        assert expected_substring in result

    def test_format_agent_result_fallback(self):
        from app.services.agent_service import _format_agent_result

        result = _format_agent_result("unknown", {"result": {"unknown_key": "value"}})
        assert result is not None
        assert len(result) > 0


class TestResetForTesting:
    def test_reset_clears_router(self):
        from app.agents.bootstrap import init_agents, reset_for_testing

        router = init_agents()
        assert AgentRegistry.list_agents()
        reset_for_testing()
        # After reset, registry should be empty
        assert not AgentRegistry.list_agents()

    def test_reinit_after_reset(self):
        from app.agents.bootstrap import init_agents, reset_for_testing

        router1 = init_agents()
        reset_for_testing()
        router2 = init_agents()
        assert router2 is not None
        assert router2 is not router1
