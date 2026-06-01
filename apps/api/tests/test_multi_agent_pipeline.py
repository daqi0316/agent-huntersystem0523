"""端到端多 Agent Pipeline 测试 — 验证统一协议、output_keys 传播、编排器。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.base import BaseAgent
from app.agents.orchestrator_agent import (
    get_orchestrator,
    PipelineOrchestrator,
    SequentialOrchestrator,
)
from app.agents.registry import AgentRegistry


# ── 模拟 Agent ──


class MockAgentA(BaseAgent):
    output_keys = ["users", "meta"]

    async def run(self, input_data: dict) -> dict:
        return self.format_result(
            "completed",
            {"users": ["alice", "bob"], "meta": {"count": 2}},
            "MockA 完成",
        )


class MockAgentB(BaseAgent):
    output_keys = ["results"]

    async def run(self, input_data: dict) -> dict:
        # 验证从 shared_context 拿到上个 Agent 的数据
        inherited = input_data.get("mocka.users", "not_found")
        return self.format_result(
            "completed",
            {"results": [f"processed:{u}" for u in inherited]},
            f"MockB 处理了 {len(inherited)} 个用户",
        )


class MockAgentFails(BaseAgent):
    output_keys = []

    async def run(self, input_data: dict) -> dict:
        msg = "模拟故障"
        raise RuntimeError(msg)


@pytest.fixture(autouse=True)
def cleanup_registry():
    AgentRegistry.clear()
    yield
    AgentRegistry.clear()


# ── get_orchestrator 工厂 ──


class TestGetOrchestrator:
    def test_auto_mode(self):
        o = get_orchestrator("auto")
        assert type(o).__name__ == "OrchestratorAgent"

    def test_pipeline_mode(self):
        o = get_orchestrator("pipeline", [])
        assert type(o).__name__ == "PipelineOrchestrator"

    def test_sequential_mode(self):
        o = get_orchestrator("sequential", ["a"])
        assert type(o).__name__ == "SequentialOrchestrator"

    def test_default_auto(self):
        o = get_orchestrator()
        assert type(o).__name__ == "OrchestratorAgent"


# ── PipelineOrchestrator ──


class TestPipelineOrchestrator:
    @pytest.mark.asyncio
    async def test_basic_pipeline(self):
        pipe = PipelineOrchestrator([MockAgentA(), MockAgentB()])
        result = await pipe.run({})

        assert result["agent"] == "pipeline"
        assert result["status"] == "completed"
        assert "流水线完成" in result["summary"]
        stages = result["result"]["stages"]
        assert len(stages) == 2
        assert stages[0]["stage"] == "mockAgentA"
        assert stages[1]["stage"] == "mockAgentB"

    @pytest.mark.asyncio
    async def test_context_propagation(self):
        pipe = PipelineOrchestrator([MockAgentA(), MockAgentB()])
        result = await pipe.run({})

        ctx = result["result"]["shared_context"]
        assert ctx["mockAgentA.users"] == ["alice", "bob"]
        assert ctx["mockAgentA.meta"] == {"count": 2}

    @pytest.mark.asyncio
    async def test_pipeline_stops_on_failure(self):
        pipe = PipelineOrchestrator([MockAgentA(), MockAgentFails(), MockAgentB()])
        result = await pipe.run({})

        stages = result["result"]["stages"]
        assert len(stages) == 2  # 停在失败 Agent
        assert stages[0]["status"] == "completed"
        assert stages[1]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_empty_pipeline(self):
        pipe = PipelineOrchestrator([])
        result = await pipe.run({})
        assert result["status"] == "completed"
        assert len(result["result"]["stages"]) == 0


# ── SequentialOrchestrator ──


class TestSequentialOrchestrator:
    @pytest.mark.asyncio
    async def test_basic_sequential(self):
        AgentRegistry.register("mocka", MockAgentA())
        AgentRegistry.register("mockb", MockAgentB())

        seq = SequentialOrchestrator(["mocka", "mockb"])
        result = await seq.run({})

        assert result["agent"] == "sequential"
        assert result["status"] == "completed"
        assert "顺序执行完成" in result["summary"]
        results = result["result"]["results"]
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_skips_missing_agent(self):
        AgentRegistry.register("mocka", MockAgentA())

        seq = SequentialOrchestrator(["mocka", "nonexistent"])
        result = await seq.run({})

        results = result["result"]["results"]
        assert len(results) == 2
        assert results[1]["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_stops_on_failure(self):
        AgentRegistry.register("mocka", MockAgentA())
        AgentRegistry.register("fail", MockAgentFails())

        seq = SequentialOrchestrator(["mocka", "fail", "mockb"])
        result = await seq.run({})

        results = result["result"]["results"]
        assert len(results) == 2
        assert results[1]["status"] == "failed"


# ── 统一输出协议 ──


class TestUnifiedProtocol:
    def test_format_result_structure(self):
        agent = MockAgentA()
        r = agent.format_result("completed", {"key": "val"}, "完成", details={"extra": "info"})
        assert r["agent"] == "mockAgentA"
        assert r["status"] == "completed"
        assert r["summary"] == "完成"
        assert r["result"] == {"key": "val"}
        assert r["details"] == {"extra": "info"}

    def test_format_result_defaults(self):
        agent = MockAgentA()
        r = agent.format_result("failed", {})
        assert r["status"] == "failed"
        assert r["summary"] == ""
        assert r["details"] == {}

    def test_agent_type_derivation(self):
        assert MockAgentA().agent_type == "mockAgentA"
        assert MockAgentB().agent_type == "mockAgentB"

    def test_output_keys_on_all_agents(self):
        from app.agents.screening_agent import ScreeningAgent
        from app.agents.sourcing_agent import SourcingAgent
        from app.agents.interview_agent import InterviewAgent
        from app.agents.offering_agent import OfferingAgent
        from app.agents.onboarding_agent import OnboardingAgent
        from app.agents.analytics_agent import AnalyticsAgent
        from app.agents.orchestrator_agent import OrchestratorAgent

        for cls in [ScreeningAgent, SourcingAgent, InterviewAgent,
                    OfferingAgent, OnboardingAgent, AnalyticsAgent,
                    OrchestratorAgent]:
            keys = getattr(cls, "output_keys", [])
            assert len(keys) > 0, f"{cls.__name__} 缺少 output_keys"
