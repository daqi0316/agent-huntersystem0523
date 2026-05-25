"""Tests for llm_chat_with_retry and raise_on_error behavior."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.retry import llm_chat_with_retry


class MockLLMClient:
    """Minimal mock LLM client that can simulate failures."""

    def __init__(self, fail_count=0, result="OK"):
        self.fail_count = fail_count
        self.result = result
        self.call_count = 0
        self._raise_on_error_calls: list[bool] = []

    async def chat(self, messages, **kwargs):
        self.call_count += 1
        self._raise_on_error_calls.append(kwargs.pop("raise_on_error", False))
        if self.call_count <= self.fail_count:
            raise ConnectionError("LLM not reachable")
        return self.result


class MockLLMClientNoRaise:
    """Mock that simulates OMLXClient's default swallow-and-fallback behavior."""

    def __init__(self, fail_count=0):
        self.fail_count = fail_count
        self.call_count = 0

    async def chat(self, messages, **kwargs):
        self.call_count += 1
        raise_on_error = kwargs.pop("raise_on_error", False)
        if self.call_count <= self.fail_count:
            if raise_on_error:
                raise ConnectionError("LLM not reachable")
            return "[LLM unavailable]"
        return "Valid response"


class TestLlmChatWithRetry:
    def test_success_on_first_try(self):
        llm = MockLLMClient(fail_count=0, result="Hello")

        result = asyncio.run(llm_chat_with_retry(llm, [{"role": "user", "content": "hi"}]))

        assert result == "Hello"
        assert llm.call_count == 1

    def test_retry_on_failure_then_succeed(self):
        llm = MockLLMClient(fail_count=2, result="Success after retry")
        msg = [{"role": "user", "content": "test"}]

        result = asyncio.run(llm_chat_with_retry(llm, msg, max_retries=3, base_delay=0.01))

        assert result == "Success after retry"
        assert llm.call_count == 3  # 2 failures + 1 success

    def test_all_retries_exhausted_raises(self):
        llm = MockLLMClient(fail_count=5, result="Never")
        msg = [{"role": "user", "content": "test"}]

        with pytest.raises(ConnectionError, match="LLM not reachable"):
            asyncio.run(llm_chat_with_retry(llm, msg, max_retries=3, base_delay=0.01))

        assert llm.call_count == 3

    def test_retry_with_omlx_style_client(self):
        """Test that retry works with the OMLXClient-style raise_on_error pattern."""
        llm = MockLLMClientNoRaise(fail_count=2)
        msg = [{"role": "user", "content": "test"}]

        result = asyncio.run(llm_chat_with_retry(llm, msg, max_retries=3, base_delay=0.01))

        assert result == "Valid response"
        assert llm.call_count == 3

    def test_all_retries_exhausted_with_no_raise_client(self):
        """When raise_on_error is False and llm returns fallback, retry still works because
        llm_chat_with_retry passes raise_on_error=True, forcing exception propagation."""
        llm = MockLLMClientNoRaise(fail_count=5)
        msg = [{"role": "user", "content": "test"}]

        with pytest.raises(ConnectionError, match="LLM not reachable"):
            asyncio.run(llm_chat_with_retry(llm, msg, max_retries=3, base_delay=0.01))

        assert llm.call_count == 3

    def test_raise_on_error_is_passed_through(self):
        """Verify the wrapper strips raise_on_error before forwarding."""
        llm = MockLLMClient(fail_count=0)

        asyncio.run(llm_chat_with_retry(llm, [{"role": "user", "content": "hi"}]))

        # Check that raise_on_error=True was passed
        assert llm._raise_on_error_calls == [True]

    def test_max_retries_custom(self):
        llm = MockLLMClient(fail_count=10)

        with pytest.raises(ConnectionError):
            asyncio.run(llm_chat_with_retry(llm, [{"role": "user", "content": "hi"}], max_retries=2, base_delay=0.01))

        assert llm.call_count == 2


class TestOmlxClientRaiseOnError:
    """Verify that the real OMLXClient/VLLMClient raise_on_error integration works."""

    async def test_raise_on_error_true_propagates(self):
        from app.llm.omlx_client import OMLXClient

        client = OMLXClient()
        # The underlying httpx client isn't patched, but we can verify the
        # raise_on_error kwarg is popped and not forwarded to the API.

        # We can't easily test this without mocking the HTTP layer — just
        # verify the method signature accepts it and doesn't crash.
        with patch.object(client, "client") as mock_http:
            mock_http.chat.completions.create = AsyncMock(
                side_effect=ConnectionError("API down")
            )
            with pytest.raises(ConnectionError, match="API down"):
                await client.chat([{"role": "user", "content": "hi"}], raise_on_error=True)

    async def test_raise_on_error_false_returns_fallback(self):
        from app.llm.omlx_client import OMLXClient

        client = OMLXClient()
        with patch.object(client, "client") as mock_http:
            mock_http.chat.completions.create = AsyncMock(
                side_effect=ConnectionError("API down")
            )
            result = await client.chat([{"role": "user", "content": "hi"}])
            assert result == "[LLM unavailable]"
