"""Tests for app.agents.base — BaseAgent abstract class."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.base import BaseAgent


class SimpleAgent(BaseAgent):
    """Concrete subclass for testing BaseAgent."""
    async def run(self, input_data: dict) -> dict:
        return self.format_result("completed", {"echo": input_data})


@pytest.fixture(autouse=True)
def _auto_clear_registry():
    """Ensure AgentRegistry is cleared before each test."""
    from app.agents.registry import AgentRegistry
    AgentRegistry.clear()
    yield


@pytest.mark.asyncio
async def test_init_with_custom_name():
    agent = SimpleAgent(name="custom_name")
    assert agent.name == "custom_name"


@pytest.mark.asyncio
async def test_init_derives_name_from_class():
    agent = SimpleAgent()
    assert agent.name == "simple"


@pytest.mark.asyncio
async def test_agent_type_derived_from_class():
    agent = SimpleAgent()
    assert agent.agent_type == "simple"


@pytest.mark.asyncio
async def test_agent_type_property():
    agent = SimpleAgent(name="custom")
    assert agent.agent_type == "simple"  # derived from class, not name


@pytest.mark.asyncio
async def test_init_handles_import_error_gracefully():
    """BaseAgent.__init__ works when AgentRegistry cannot be imported (line 50-51)."""
    with patch.dict("sys.modules", {"app.agents.registry": None}):
        with patch("builtins.__import__", side_effect=ImportError("No registry")):
            agent = SimpleAgent(name="isolated")
            assert agent.name == "isolated"


@pytest.mark.asyncio
async def test_system_prompt_lazy_loads_from_file():
    agent = SimpleAgent(name="lazy_load_test")
    assert agent._system_prompt == ""

    with patch("app.agents.base.load_prompt", return_value="loaded prompt") as mock_load:
        prompt = agent.system_prompt
        assert prompt == "loaded prompt"
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_system_prompt_cache():
    """Second access does NOT re-call load_prompt."""
    agent = SimpleAgent(name="cache_test")
    with patch("app.agents.base.load_prompt", return_value="cached") as mock_load:
        _ = agent.system_prompt  # first access
        _ = agent.system_prompt  # second access
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_system_prompt_setter_overrides_file():
    """Setting system_prompt directly overrides file-loaded value (line 68)."""
    agent = SimpleAgent(name="override_test")
    agent.system_prompt = "custom prompt"
    assert agent.system_prompt == "custom prompt"


@pytest.mark.asyncio
async def test_load_system_prompt_with_content():
    """_load_system_prompt returns content and logs debug when file exists (line 118-124)."""
    agent = SimpleAgent(name="content_test")
    with patch("app.agents.base.load_prompt", return_value="some content") as mock_load:
        with patch("app.agents.base.logger") as mock_logger:
            prompt = agent._load_system_prompt()
            assert prompt == "some content"
            mock_load.assert_called_once()
            mock_logger.debug.assert_called_once()


@pytest.mark.asyncio
async def test_load_system_prompt_with_empty_content():
    """_load_system_prompt returns empty string and logs debug when no prompt found."""
    agent = SimpleAgent(name="empty_test")
    with patch("app.agents.base.load_prompt", return_value=""):
        with patch("app.agents.base.logger") as mock_logger:
            prompt = agent._load_system_prompt()
            assert prompt == ""
            mock_logger.debug.assert_called_once()


@pytest.mark.asyncio
async def test_format_result_defaults():
    """format_result produces correct dict structure."""
    agent = SimpleAgent(name="format_test")
    result = agent.format_result("completed", {"key": "value"}, summary="done")
    assert result == {
        "agent": "format_test",
        "status": "completed",
        "summary": "done",
        "result": {"key": "value"},
        "details": {},
    }


@pytest.mark.asyncio
async def test_format_result_with_details():
    """format_result includes details when provided."""
    agent = SimpleAgent(name="fmt")
    result = agent.format_result("failed", {}, details={"error": "timeout"})
    assert result["details"] == {"error": "timeout"}
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_derive_name_drops_agent_suffix():
    """_derive_name strips 'Agent' suffix and lowercases first letter."""
    class MyCustomAgent(BaseAgent):
        async def run(self, input_data): return {}

    agent = MyCustomAgent()
    assert agent.name == "myCustom"


@pytest.mark.asyncio
async def test_derive_name_no_suffix():
    """_derive_name handles class names not ending in 'Agent'."""
    class JustName(BaseAgent):
        async def run(self, input_data): return {}

    agent = JustName()
    assert agent.name == "justName"


@pytest.mark.asyncio
async def test_run_interface_returns_unified_format():
    """The concrete agent's run() returns the unified format."""
    agent = SimpleAgent(name="runner")
    output = await agent.run({"hello": "world"})
    assert output["agent"] == "runner"
    assert output["status"] == "completed"
    assert output["result"] == {"echo": {"hello": "world"}}
