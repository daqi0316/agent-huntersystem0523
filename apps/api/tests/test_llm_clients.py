"""LLM client tests — mock AsyncOpenAI for OMLXClient, VLLMClient, factory."""

from unittest.mock import AsyncMock, patch

import pytest

from app.llm import get_llm_client
from app.llm.omlx_client import OMLXClient
from app.llm.vllm_client import VLLMClient

pytestmark = pytest.mark.asyncio


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_settings():
    """Default mock settings — override per-test as needed."""
    with patch("app.llm.settings") as mock_s:
        mock_s.llm_provider = "omlx"
        mock_s.llm_base_url = "http://localhost:8001/v1"
        mock_s.llm_api_key = "sk-test"
        mock_s.llm_model = "qwen3.6"
        mock_s.llm_embed_model = "bge-m3"
        yield mock_s


def _build_mock_openai():
    """Build a mock AsyncOpenAI that returns controlled responses."""
    mock_client = AsyncMock()

    # Chat mock
    mock_message = AsyncMock()
    mock_message.content = "Hello! I am an AI assistant."
    mock_choice = AsyncMock()
    mock_choice.message = mock_message
    mock_chat_resp = AsyncMock()
    mock_chat_resp.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_chat_resp)

    # Embed mock
    mock_datum = AsyncMock()
    mock_datum.embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    mock_embed_resp = AsyncMock()
    mock_embed_resp.data = [mock_datum]
    mock_client.embeddings.create = AsyncMock(return_value=mock_embed_resp)

    return mock_client


# ── OMLXClient tests ─────────────────────────────────────────────────────


class TestOMLXClient:
    async def test_chat_success(self):
        mock_client = _build_mock_openai()
        with patch("app.llm.omlx_client.AsyncOpenAI", return_value=mock_client):
            client = OMLXClient()
            result = await client.chat([{"role": "user", "content": "hi"}])

        assert result == "Hello! I am an AI assistant."

    async def test_chat_fallback_on_exception(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("LLM unreachable")
        )
        with patch("app.llm.omlx_client.AsyncOpenAI", return_value=mock_client):
            client = OMLXClient()
            result = await client.chat([{"role": "user", "content": "hi"}])

        assert result == "[LLM unavailable]"

    async def test_embed_success(self):
        mock_client = _build_mock_openai()
        with patch("app.llm.omlx_client.AsyncOpenAI", return_value=mock_client):
            client = OMLXClient()
            result = await client.embed("test text")

        assert result == [0.1, 0.2, 0.3, 0.4, 0.5]

    async def test_embed_fallback_on_exception(self):
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(
            side_effect=Exception("Embedding failed")
        )
        with patch("app.llm.omlx_client.AsyncOpenAI", return_value=mock_client):
            client = OMLXClient()
            result = await client.embed("test text")

        assert result == []


# ── VLLMClient tests ─────────────────────────────────────────────────────


class TestVLLMClient:
    async def test_chat_success(self):
        mock_client = _build_mock_openai()
        with patch("app.llm.vllm_client.AsyncOpenAI", return_value=mock_client):
            client = VLLMClient()
            result = await client.chat([{"role": "user", "content": "hi"}])

        assert result == "Hello! I am an AI assistant."

    async def test_chat_fallback_on_exception(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("vLLM down")
        )
        with patch("app.llm.vllm_client.AsyncOpenAI", return_value=mock_client):
            client = VLLMClient()
            result = await client.chat([{"role": "user", "content": "hi"}])

        assert result == "[LLM unavailable]"

    async def test_embed_success(self):
        mock_client = _build_mock_openai()
        with patch("app.llm.vllm_client.AsyncOpenAI", return_value=mock_client):
            client = VLLMClient()
            result = await client.embed("test text")

        assert result == [0.1, 0.2, 0.3, 0.4, 0.5]

    async def test_embed_fallback_on_exception(self):
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(
            side_effect=Exception("Embed failed")
        )
        with patch("app.llm.vllm_client.AsyncOpenAI", return_value=mock_client):
            client = VLLMClient()
            result = await client.embed("test text")

        assert result == []


# ── Factory tests ──────────────────────────────────────────────────────────


class TestGetLLMClient:
    async def test_returns_omlx_by_default(self, mock_settings):
        mock_settings.llm_provider = "omlx"
        client = get_llm_client()
        assert isinstance(client, OMLXClient)

    async def test_returns_vllm_when_configured(self, mock_settings):
        mock_settings.llm_provider = "vllm"
        client = get_llm_client()
        assert isinstance(client, VLLMClient)

    async def test_case_insensitive_provider(self, mock_settings):
        mock_settings.llm_provider = "VLLM"
        client = get_llm_client()
        assert isinstance(client, VLLMClient)
