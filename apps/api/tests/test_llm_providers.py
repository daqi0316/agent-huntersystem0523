"""Tests for app.llm.provider — Provider implementations + error classification."""

from unittest.mock import AsyncMock, patch

import pytest

from app.llm.provider.base import (
    ErrorCategory,
    ProviderError,
    Strategy,
    STRATEGY,
)


class TestErrorCategory:
    def test_all_categories_have_strategy(self):
        for cat in ErrorCategory:
            assert cat in STRATEGY, f"{cat} missing from STRATEGY"

    def test_auth_not_retryable(self):
        s = STRATEGY[ErrorCategory.AUTH]
        assert not s.retryable
        assert not s.fallback
        assert s.alert

    def test_rate_limit_retryable_no_fallback(self):
        s = STRATEGY[ErrorCategory.RATE_LIMIT]
        assert s.retryable
        assert not s.fallback
        assert not s.alert

    def test_server_error_retryable_and_fallback(self):
        s = STRATEGY[ErrorCategory.SERVER_ERROR]
        assert s.retryable
        assert s.fallback
        assert s.alert

    def test_timeout_retryable_and_fallback(self):
        s = STRATEGY[ErrorCategory.TIMEOUT]
        assert s.retryable
        assert s.fallback
        assert not s.alert

    def test_unknown_no_retry_but_fallback(self):
        s = STRATEGY[ErrorCategory.UNKNOWN]
        assert not s.retryable
        assert s.fallback
        assert s.alert


class TestProviderError:
    def test_auth_should_not_fallback(self):
        err = ProviderError(ErrorCategory.AUTH, "invalid key")
        assert not err.should_retry()
        assert not err.should_fallback()
        assert err.should_alert()

    def test_server_error_should_fallback(self):
        err = ProviderError(ErrorCategory.SERVER_ERROR, "500 internal error")
        assert err.should_retry()
        assert err.should_fallback()
        assert err.should_alert()

    def test_rate_limit_should_retry_no_fallback(self):
        err = ProviderError(ErrorCategory.RATE_LIMIT, "429 too many")
        assert err.should_retry()
        assert not err.should_fallback()
        assert not err.should_alert()

    def test_str_representation(self):
        err = ProviderError(ErrorCategory.AUTH, "bad key")
        assert "[auth]" in str(err)

    def test_with_status_code(self):
        err = ProviderError(ErrorCategory.SERVER_ERROR, "error", status_code=503)
        assert err.status_code == 503


class TestOpenAICompatProvider:
    @pytest.fixture
    def provider(self):
        from app.llm.provider.openai_compat import OpenAICompatProvider
        p = OpenAICompatProvider()
        p._client_cache.clear()
        return p

    @pytest.mark.asyncio
    async def test_auth_error_mapped(self, provider):
        """AuthenticationError → ErrorCategory.AUTH"""
        with patch.object(provider, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.side_effect = __import__("openai").AuthenticationError(
                "invalid key",
                response=AsyncMock(status_code=401),
                body={"error": "invalid"},
            )
            mock_get.return_value = mock_client

            with pytest.raises(ProviderError) as exc:
                await provider.chat("test-model", [{"role": "user", "content": "hi"}], base_url="http://x", api_key="bad")
            assert exc.value.category == ErrorCategory.AUTH

    @pytest.mark.asyncio
    async def test_rate_limit_error_mapped(self, provider):
        with patch.object(provider, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.side_effect = __import__("openai").RateLimitError(
                "rate limited",
                response=AsyncMock(status_code=429),
                body={"error": "rate"},
            )
            mock_get.return_value = mock_client

            with pytest.raises(ProviderError) as exc:
                await provider.chat("test-model", [{"role": "user", "content": "hi"}], base_url="http://x", api_key="k")
            assert exc.value.category == ErrorCategory.RATE_LIMIT

    @pytest.mark.asyncio
    async def test_timeout_error_mapped(self, provider):
        with patch.object(provider, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.side_effect = __import__("openai").APITimeoutError("timeout")
            mock_get.return_value = mock_client

            with pytest.raises(ProviderError) as exc:
                await provider.chat("test-model", [{"role": "user", "content": "hi"}], base_url="http://x", api_key="k")
            assert exc.value.category == ErrorCategory.TIMEOUT

    @pytest.mark.asyncio
    async def test_invalid_model_error_mapped(self, provider):
        with patch.object(provider, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.side_effect = __import__("openai").NotFoundError(
                "model not found",
                response=AsyncMock(status_code=404),
                body={"error": "not found"},
            )
            mock_get.return_value = mock_client

            with pytest.raises(ProviderError) as exc:
                await provider.chat("nonexistent", [{"role": "user", "content": "hi"}], base_url="http://x", api_key="k")
            assert exc.value.category == ErrorCategory.INVALID_MODEL

    def test_invalidate_client(self, provider):
        provider._client_cache["http://test"] = AsyncMock()
        assert "http://test" in provider._client_cache
        provider.invalidate_client("http://test")
        assert "http://test" not in provider._client_cache

    def test_invalidate_all(self, provider):
        provider._client_cache["http://a"] = AsyncMock()
        provider._client_cache["http://b"] = AsyncMock()
        provider.invalidate_all()
        assert len(provider._client_cache) == 0


class TestAnthropicProvider:
    @pytest.fixture
    def provider(self):
        from app.llm.provider.anthropic import AnthropicProvider
        return AnthropicProvider()

    def test_provider_type(self, provider):
        assert provider.provider_type == "anthropic"

    def test_convert_messages(self, provider):
        openai_msgs = [
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = provider._convert_messages(openai_msgs)
        # system message should be skipped (passed separately)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == [{"type": "text", "text": "hello"}]
        assert result[1]["role"] == "assistant"

    def test_convert_tools(self, provider):
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                },
            }
        ]
        result = provider._convert_tools(openai_tools)
        assert result is not None
        assert result[0]["name"] == "get_weather"
        assert "input_schema" in result[0]
        assert "parameters" not in result[0]

    def test_convert_tools_none(self, provider):
        assert provider._convert_tools(None) is None
        assert provider._convert_tools([]) is None

    @pytest.mark.asyncio
    async def test_chat_no_api_key(self, provider):
        with pytest.raises(ProviderError) as exc:
            await provider.chat("claude-3", [{"role": "user", "content": "hi"}], api_key="", base_url="")
        assert exc.value.category == ErrorCategory.AUTH


class TestProviderPool:
    @pytest.fixture
    def pool(self):
        from app.llm.provider.pool import ProviderPool
        p = ProviderPool()
        return p

    @pytest.mark.asyncio
    async def test_get_openai_compat(self, pool):
        provider = await pool.get_provider("openai_compat")
        from app.llm.provider.openai_compat import OpenAICompatProvider
        assert isinstance(provider, OpenAICompatProvider)

    @pytest.mark.asyncio
    async def test_get_anthropic(self, pool):
        provider = await pool.get_provider("anthropic")
        from app.llm.provider.anthropic import AnthropicProvider
        assert isinstance(provider, AnthropicProvider)

    @pytest.mark.asyncio
    async def test_invalid_provider_type(self, pool):
        with pytest.raises(ValueError):
            await pool.get_provider("nonexistent")

    @pytest.mark.asyncio
    async def test_provider_cached(self, pool):
        p1 = await pool.get_provider("openai_compat")
        p2 = await pool.get_provider("openai_compat")
        assert p1 is p2  # same instance

    @pytest.mark.asyncio
    async def test_invalidate(self, pool):
        p1 = await pool.get_provider("openai_compat")
        pool.invalidate("openai_compat")
        p2 = await pool.get_provider("openai_compat")
        assert p1 is not p2  # new instance after invalidate
