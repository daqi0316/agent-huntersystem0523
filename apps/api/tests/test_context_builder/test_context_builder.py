"""Tests for ContextBuilder — token-aware prompt assembly."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.context_builder import (
    ContextBuilder,
    count_tokens,
    count_message_tokens,
    count_messages_tokens,
    HISTORY_BUDGET,
    TOOL_RESULT_HISTORY_BUDGET,
    TOOL_RESULT_TOKENS,
    DEFAULT_MAX_TOKENS,
)


class TestCountTokens:
    def test_count_tokens_fallback(self) -> None:
        result = count_tokens("hello world", model="unknown-model")
        assert result > 0

    def test_count_tokens_chinese(self) -> None:
        result = count_tokens("你好世界", model="gpt-4o")
        assert result > 0

    def test_count_message_tokens(self) -> None:
        msg = {"role": "user", "content": "hello"}
        result = count_message_tokens(msg)
        assert result > 0

    def test_count_messages_tokens(self) -> None:
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = count_messages_tokens(msgs)
        assert result > 0


class TestBuildHistory:
    @pytest.fixture
    def cb(self) -> ContextBuilder:
        db = AsyncMock()
        llm = MagicMock()
        llm.model = "gpt-4o"
        qdrant = MagicMock()
        return ContextBuilder(db=db, llm=llm, qdrant=qdrant, model="gpt-4o")

    @pytest.mark.asyncio
    async def test_empty_messages(self, cb: ContextBuilder) -> None:
        result = await cb._build_history([])
        assert result == []

    @pytest.mark.asyncio
    async def test_under_budget(self, cb: ContextBuilder) -> None:
        msgs = [{"role": "user", "content": "hi"}] * 3
        result = await cb._build_history(msgs)
        assert result == msgs

    @pytest.mark.asyncio
    async def test_over_budget_truncates_from_oldest(self, cb: ContextBuilder) -> None:
        # Each msg ~2500 tokens; 50 msgs ≈ 125k > 113k budget → truncate
        msgs = [{"role": "user", "content": f"msg_{i}_" + "x" * 9900} for i in range(50)]
        result = await cb._build_history(msgs)
        assert len(result) < 50
        assert result[-1] == msgs[-1]
        assert result[0]["content"].startswith("msg_")

    @pytest.mark.asyncio
    async def test_at_least_one_message_preserved(self, cb: ContextBuilder) -> None:
        msgs = [{"role": "user", "content": "x" * 10000}]
        result = await cb._build_history(msgs)
        assert len(result) >= 1


class TestBuildSystem:
    @pytest.mark.asyncio
    async def test_returns_system_message(self) -> None:
        db = AsyncMock()
        llm = MagicMock()
        llm.model = "gpt-4o"
        qdrant = MagicMock()
        cb = ContextBuilder(db=db, llm=llm, qdrant=qdrant, model="gpt-4o")
        result = await cb._build_system("user-1")
        assert result["role"] == "system"
        assert "招聘" in result["content"]

    @pytest.mark.asyncio
    async def test_memory_injection_failure_is_non_blocking(self) -> None:
        db = AsyncMock()
        llm = MagicMock()
        llm.model = "gpt-4o"
        qdrant = MagicMock()
        qdrant.query_points = AsyncMock(side_effect=RuntimeError("qdrant down"))
        cb = ContextBuilder(db=db, llm=llm, qdrant=qdrant, model="gpt-4o")
        result = await cb._build_system("user-1")
        assert result["role"] == "system"
        assert "招聘" in result["content"]


class TestBuild:
    @pytest.mark.asyncio
    async def test_build_returns_system_plus_history(self) -> None:
        db = AsyncMock()
        llm = MagicMock()
        llm.model = "gpt-4o"
        qdrant = MagicMock()
        cb = ContextBuilder(db=db, llm=llm, qdrant=qdrant, model="gpt-4o")
        msgs = [{"role": "user", "content": "hi"}]
        result = await cb.build("user-1", msgs)
        assert result[0]["role"] == "system"
        assert len(result) >= 1


class TestBuildWithTools:
    @pytest.fixture
    def cb(self) -> ContextBuilder:
        db = AsyncMock()
        llm = MagicMock()
        llm.model = "gpt-4o"
        qdrant = MagicMock()
        return ContextBuilder(db=db, llm=llm, qdrant=qdrant, model="gpt-4o")

    @pytest.mark.asyncio
    async def test_empty_tool_calls(self, cb: ContextBuilder) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        result = await cb.build_with_tools("user-1", msgs, None, [], [])
        assert len(result) >= 1
        assert result[0]["role"] == "system"

    @pytest.mark.asyncio
    async def test_with_tool_calls_and_results(self, cb: ContextBuilder) -> None:
        msgs = [{"role": "user", "content": "search python"}]
        tool_calls = [
            {"id": "call_1", "function": {"name": "search", "arguments": "{}"}}
        ]
        tool_results = [{"tool": "search", "result": {"candidates": ["zhangsan"]}}]
        result = await cb.build_with_tools(
            "user-1", msgs, None, tool_calls, tool_results
        )
        assert result[0]["role"] == "system"
        roles = [m["role"] for m in result]
        assert "assistant" in roles
        assert "tool" in roles

    @pytest.mark.asyncio
    async def test_tool_results_truncated_when_too_large(self, cb: ContextBuilder) -> None:
        msgs = [{"role": "user", "content": "search"}]
        tool_calls = [{"id": f"call_{i}", "function": {"name": "search", "arguments": "{}"}} for i in range(10)]
        tool_results = [
            {"tool": "search", "result": {"data": "x" * 5000}}
            for _ in range(10)
        ]
        result = await cb.build_with_tools(
            "user-1", msgs, None, tool_calls, tool_results
        )
        total = count_messages_tokens(result)
        assert total < DEFAULT_MAX_TOKENS

    @pytest.mark.asyncio
    async def test_assistant_content_preserved(self, cb: ContextBuilder) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        tool_calls = [
            {"id": "call_1", "function": {"name": "search", "arguments": "{}"}}
        ]
        tool_results = [{"tool": "search", "result": {"found": 1}}]
        result = await cb.build_with_tools(
            "user-1", msgs, "I found 1 result", tool_calls, tool_results
        )
        assistant_msgs = [m for m in result if m.get("role") == "assistant"]
        assert any("I found 1 result" in str(m) or m.get("content") == "I found 1 result" for m in assistant_msgs)


class TestBudgetConstants:
    def test_history_budget_is_positive(self) -> None:
        assert HISTORY_BUDGET > 0

    def test_tool_result_budget_is_positive(self) -> None:
        assert TOOL_RESULT_HISTORY_BUDGET > 0

    def test_history_plus_memory_within_max(self) -> None:
        from app.core.context_builder import SYSTEM_TOKENS, MEMORY_TOKENS
        assert SYSTEM_TOKENS + MEMORY_TOKENS + HISTORY_BUDGET <= DEFAULT_MAX_TOKENS


class TestFormatToolCalls:
    @pytest.fixture
    def cb(self) -> ContextBuilder:
        db = AsyncMock()
        llm = MagicMock()
        llm.model = "gpt-4o"
        return ContextBuilder(db=db, llm=llm, qdrant=MagicMock(), model="gpt-4o")

    def test_empty_tool_calls(self, cb: ContextBuilder) -> None:
        result = cb._format_tool_calls([], None)
        assert result == []

    def test_single_tool_call(self, cb: ContextBuilder) -> None:
        tool_calls = [
            {
                "id": "call_1",
                "function": {"name": "search_candidates", "arguments": '{"skill": "python"}'},
            }
        ]
        result = cb._format_tool_calls(tool_calls, None)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["tool_calls"][0]["function"]["name"] == "search_candidates"

    def test_assistant_content_included(self, cb: ContextBuilder) -> None:
        tool_calls = [
            {"id": "call_1", "function": {"name": "search", "arguments": "{}"}}
        ]
        result = cb._format_tool_calls(tool_calls, "found 3 candidates")
        assert result[0]["content"] == "found 3 candidates"


class TestFormatToolResults:
    @pytest.fixture
    def cb(self) -> ContextBuilder:
        db = AsyncMock()
        llm = MagicMock()
        llm.model = "gpt-4o"
        return ContextBuilder(db=db, llm=llm, qdrant=MagicMock(), model="gpt-4o")

    def test_empty_results(self, cb: ContextBuilder) -> None:
        result = cb._format_tool_results([], [])
        assert result == []

    def test_error_result(self, cb: ContextBuilder) -> None:
        tool_calls = [{"id": "call_1", "function": {"name": "search", "arguments": "{}"}}]
        tool_results = [{"tool": "search", "error": "API timeout"}]
        result = cb._format_tool_results(tool_calls, tool_results)
        assert len(result) == 1
        assert "error" in result[0]["content"]

    def test_success_result(self, cb: ContextBuilder) -> None:
        tool_calls = [{"id": "call_1", "function": {"name": "search", "arguments": "{}"}}]
        tool_results = [{"tool": "search", "result": {"count": 5}}]
        result = cb._format_tool_results(tool_calls, tool_results)
        assert len(result) == 1
        assert "count" in result[0]["content"]


class TestTruncateToolMessages:
    @pytest.fixture
    def cb(self) -> ContextBuilder:
        db = AsyncMock()
        llm = MagicMock()
        llm.model = "gpt-4o"
        return ContextBuilder(db=db, llm=llm, qdrant=MagicMock(), model="gpt-4o")

    @pytest.mark.asyncio
    async def test_truncation_loop_body(self, cb: ContextBuilder) -> None:
        """Lines 289-297: _truncate_tool_messages actual loop body executes."""
        msgs = [
            {"role": "tool", "tool_call_id": f"call_{i}", "content": "x" * 5000}
            for i in range(10)
        ]
        # Small budget forces the loop to break before consuming all
        budget = 200
        result = cb._truncate_tool_messages(msgs, budget)
        assert len(result) < 10

    @pytest.mark.asyncio
    async def test_remaining_negative_double_truncation(self, cb: ContextBuilder) -> None:
        """Lines 209-212: remaining < 0 forces double truncation of both blocks."""
        msgs = [{"role": "user", "content": "x" * 1000}]
        tool_calls = [
            {"id": f"call_{i}", "function": {"name": "f", "arguments": "{}"}}
            for i in range(20)
        ]
        tool_results = [
            {"tool": "f", "result": {"data": "y" * 5000}}
            for _ in range(20)
        ]
        result = await cb.build_with_tools(
            "user-1", msgs, None, tool_calls, tool_results
        )
        total = count_messages_tokens(result, "gpt-4o")
        assert total < 120000


class TestCountTokensEdge:
    def test_count_tokens_fallback_path(self) -> None:
        """Lines 46-51: tiktoken.get_encoding failure triggers char-based fallback."""
        # Force the fallback by patching _get_encoding to return None
        import app.core.context_builder as cb_module
        orig = cb_module._get_encoding
        cb_module._get_encoding = lambda m: None
        try:
            result = count_tokens("hello world", "gpt-4o")
            assert result > 0
            assert isinstance(result, int)
        finally:
            cb_module._get_encoding = orig

    def test_count_tokens_exception_in_encode(self) -> None:
        """Lines 61-63: encode() throws → falls back to char-based estimate."""
        import app.core.context_builder as cb_module
        enc = MagicMock()
        enc.encode.side_effect = RuntimeError("encode failed")
        orig_cache = cb_module._ENCODING_CACHE.copy()
        cb_module._ENCODING_CACHE["gpt-4o"] = enc
        try:
            result = count_tokens("hello world", "gpt-4o")
            assert result > 0
        finally:
            cb_module._ENCODING_CACHE.clear()
            cb_module._ENCODING_CACHE.update(orig_cache)


class TestQdrantNone:
    @pytest.mark.asyncio
    async def test_qdrant_client_is_none_path(self) -> None:
        """Lines 120-124: self.qdrant is None → get_qdrant() called."""
        db = AsyncMock()
        llm = MagicMock()
        llm.model = "gpt-4o"
        cb = ContextBuilder(db=db, llm=llm, qdrant=None, model="gpt-4o")
        result = await cb._build_system("user-1")
        assert result["role"] == "system"
        assert "招聘" in result["content"]
