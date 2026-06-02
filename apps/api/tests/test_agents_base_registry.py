"""Tests for app/agents/base.py + app/agents/registry.py.

覆盖 base.py 26 missed (66%) + registry.py 8 missed (74%):
- base.py: _derive_name, _derive_agent_type, _load_system_prompt, system_prompt property, format_result, _record_operation_start/end, _operation_id, __init__, output_keys
- registry.py: register, resolve, list_agents, get_status, unregister, clear
"""

from __future__ import annotations

import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry


# ─── Concrete test agents (no underscore prefix → clean derived names) ──


class StubAgent(BaseAgent):
    output_keys = ["score", "verdict"]

    async def run(self, input_data: dict) -> dict:
        return self.format_result(
            status="completed",
            result={"score": 95, "verdict": "ok"},
            summary="stub done",
            details={"input": input_data},
        )


class NoSuffixAgent(BaseAgent):
    async def run(self, input_data: dict) -> dict:
        return self.format_result("completed", {})


# ─── _derive_name / _derive_agent_type ────────────────────────────────


class TestDeriveName:
    def test_strips_agent_suffix(self):
        agent = StubAgent()
        assert agent.name == "stub"

    def test_no_suffix_kept_lowercased(self):
        agent = NoSuffixAgent()
        assert agent.name.startswith("no")
        assert agent.name[0].islower()

    def test_empty_name_returns_unknown(self):
        class EmptyAgent(BaseAgent):
            async def run(self, d):
                return self.format_result("completed", {})

        agent = EmptyAgent()
        assert agent._derive_name() == "empty"

    def test_single_char_class(self):
        class AAgent(BaseAgent):
            async def run(self, d):
                return self.format_result("completed", {})

        agent = AAgent()
        assert agent.name == "a"

    def test_explicit_name_override(self):
        agent = StubAgent(name="custom_name")
        assert agent.name == "custom_name"

    def test_agent_type_delegates_to_name(self):
        agent = StubAgent()
        assert agent.agent_type == agent.name == "stub"
        assert agent._agent_type == "stub"


# ─── _load_system_prompt + system_prompt property ──────────────────────


class TestSystemPrompt:
    def test_load_system_prompt_calls_load_prompt(self):
        agent = StubAgent()
        with patch("app.agents.base.load_prompt", return_value="prompt text") as lp:
            result = agent._load_system_prompt()
        lp.assert_called_once_with("stub")
        assert result == "prompt text"

    def test_load_system_prompt_empty(self):
        agent = StubAgent()
        with patch("app.agents.base.load_prompt", return_value="") as lp:
            result = agent._load_system_prompt()
        assert result == ""

    def test_system_prompt_lazy_loads(self):
        agent = StubAgent()
        assert agent._system_prompt == ""
        with patch.object(agent, "_load_system_prompt", return_value="lazy") as lp:
            assert agent.system_prompt == "lazy"
            lp.assert_called_once()

    def test_system_prompt_caches(self):
        agent = StubAgent()
        with patch.object(agent, "_load_system_prompt", return_value="cached") as lp:
            agent.system_prompt
            agent.system_prompt
            assert lp.call_count == 1

    def test_system_prompt_setter_overrides(self):
        agent = StubAgent()
        agent.system_prompt = "manual override"
        assert agent.system_prompt == "manual override"


# ─── format_result ──────────────────────────────────────────────────────


class TestFormatResult:
    def test_full(self):
        agent = StubAgent()
        result = agent.format_result(
            status="completed",
            result={"x": 1},
            summary="test summary",
            details={"k": "v"},
        )
        assert result == {
            "agent": "stub",
            "status": "completed",
            "summary": "test summary",
            "result": {"x": 1},
            "details": {"k": "v"},
        }

    def test_default_details_empty(self):
        agent = StubAgent()
        result = agent.format_result(status="completed", result={})
        assert result["details"] == {}
        assert result["summary"] == ""

    def test_none_details_becomes_empty(self):
        agent = StubAgent()
        result = agent.format_result(status="failed", result={}, details=None)
        assert result["details"] == {}


# ─── _operation_id ─────────────────────────────────────────────────────


class TestOperationId:
    def test_default_empty_string(self):
        agent = StubAgent()
        assert agent._operation_id() == ""

    def test_returns_current_op_id(self):
        agent = StubAgent()
        agent._current_op_id = "op-123"
        assert agent._operation_id() == "op-123"


# ─── _record_operation_start ──────────────────────────────────────────


class TestRecordOperationStart:
    async def test_success_returns_op_id(self):
        agent = StubAgent()
        mock_op = MagicMock()
        mock_op.id = "op-new"

        async def fake_create(**kwargs):
            return mock_op

        async def fake_transition(op_id, status):
            return mock_op

        mock_svc = MagicMock()
        mock_svc.create = fake_create
        mock_svc.transition = fake_transition

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.operation_service.OperationService", return_value=mock_svc), \
             patch("app.core.database.AsyncSessionLocal", return_value=mock_db):
            result = await agent._record_operation_start(
                action="screen", input_summary="test", user_id="u-1",
            )
        assert result == "op-new"
        assert agent._current_op_id == "op-new"

    async def test_failure_returns_empty_string(self):
        agent = StubAgent()
        with patch("app.services.operation_service.OperationService", side_effect=RuntimeError("boom")):
            result = await agent._record_operation_start(action="x")
        assert result == ""
        assert getattr(agent, "_current_op_id", "") == ""


# ─── _record_operation_end ────────────────────────────────────────────


class TestRecordOperationEnd:
    async def test_empty_op_id_skips(self):
        agent = StubAgent()
        with patch("app.services.operation_service.OperationService") as mock_cls:
            await agent._record_operation_end(operation_id="", output_summary="x")
        mock_cls.assert_not_called()

    async def test_success_calls_complete(self):
        agent = StubAgent()

        mock_svc = MagicMock()
        mock_svc.complete = AsyncMock()

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.operation_service.OperationService", return_value=mock_svc), \
             patch("app.core.database.AsyncSessionLocal", return_value=mock_db):
            await agent._record_operation_end(
                operation_id="op-1", output_summary="done", success=True,
            )
        mock_svc.complete.assert_called_once_with("op-1", output_summary="done")

    async def test_failure_calls_fail(self):
        agent = StubAgent()

        mock_svc = MagicMock()
        mock_svc.fail = AsyncMock()

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.operation_service.OperationService", return_value=mock_svc), \
             patch("app.core.database.AsyncSessionLocal", return_value=mock_db):
            await agent._record_operation_end(
                operation_id="op-1", error="boom", success=False,
            )
        mock_svc.fail.assert_called_once_with("op-1", error_message="boom")

    async def test_exception_swallowed(self):
        agent = StubAgent()
        with patch("app.services.operation_service.OperationService", side_effect=RuntimeError("db down")):
            await agent._record_operation_end(operation_id="op-1", success=True)


# ─── __init__ ──────────────────────────────────────────────────────────


class TestInit:
    def test_default_init(self):
        agent = StubAgent()
        assert agent.name == "stub"
        assert agent._agent_type == "stub"
        assert agent._system_prompt == ""

    def test_explicit_name(self):
        agent = StubAgent(name="custom")
        assert agent.name == "custom"

    def test_init_with_registry_import_error(self):
        with patch("app.agents.registry.AgentRegistry.register", side_effect=ImportError):
            with warnings.catch_warnings():
                agent = StubAgent()
            assert agent.name == "stub"


# ─── output_keys ───────────────────────────────────────────────────────


class TestOutputKeys:
    def test_default_empty(self):
        class BareAgent(BaseAgent):
            async def run(self, d):
                return self.format_result("completed", {})

        assert BareAgent.output_keys == []

    def test_subclass_declaration(self):
        assert StubAgent.output_keys == ["score", "verdict"]


# ═══════════════════════════════════════════════════════════════════════
# AgentRegistry tests
# ═══════════════════════════════════════════════════════════════════════


class TestRegistryRegister:
    def test_register_new(self):
        AgentRegistry.clear()
        agent = StubAgent()
        assert "stub" in AgentRegistry.list_agents()
        assert AgentRegistry.resolve("stub") is agent

    def test_register_duplicate_emits_warning(self):
        AgentRegistry.clear()
        agent1 = StubAgent()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent2 = StubAgent()
        assert any("覆盖已注册的 agent" in str(warning.message) for warning in w)


class TestRegistryResolve:
    def test_resolve_existing(self):
        AgentRegistry.clear()
        agent = StubAgent()
        assert AgentRegistry.resolve("stub") is agent

    def test_resolve_missing_returns_none(self):
        AgentRegistry.clear()
        assert AgentRegistry.resolve("nonexistent") is None


class TestRegistryListAgents:
    def test_empty(self):
        AgentRegistry.clear()
        assert AgentRegistry.list_agents() == []

    def test_lists_all(self):
        AgentRegistry.clear()
        StubAgent()
        assert "stub" in AgentRegistry.list_agents()


class TestRegistryGetStatus:
    def test_not_found(self):
        AgentRegistry.clear()
        status = AgentRegistry.get_status("ghost")
        assert status == {"name": "ghost", "registered": False, "error": "not_found"}

    def test_registered(self):
        AgentRegistry.clear()
        StubAgent()
        status = AgentRegistry.get_status("stub")
        assert status["name"] == "stub"
        assert status["registered"] is True
        assert status["type"] == "StubAgent"
        assert "has_system_prompt" in status


class TestRegistryUnregister:
    def test_unregister_existing(self):
        AgentRegistry.clear()
        StubAgent()
        assert AgentRegistry.unregister("stub") is True
        assert AgentRegistry.resolve("stub") is None

    def test_unregister_nonexistent(self):
        AgentRegistry.clear()
        assert AgentRegistry.unregister("ghost") is False


class TestRegistryClear:
    def test_clear_removes_all(self):
        AgentRegistry.clear()
        StubAgent()
        assert len(AgentRegistry.list_agents()) > 0
        AgentRegistry.clear()
        assert AgentRegistry.list_agents() == []
