"""Integration tests — full chain from get_llm_client() through Router to Provider."""

from unittest.mock import AsyncMock, patch

import pytest

from app.llm import get_llm_client, reset_llm_client


@pytest.mark.asyncio
async def test_get_llm_client_db_primary():
    """DB has primary -> get_llm_client() returns _RouterLLMAdapter."""
    reset_llm_client()
    with patch("app.core.database.AsyncSessionLocal") as mock_session:
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_db
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = AsyncMock()
        mock_db.execute.return_value = mock_result

        client = await get_llm_client()
        from app.llm import _RouterLLMAdapter
        assert isinstance(client, _RouterLLMAdapter)





@pytest.mark.asyncio
async def test_router_adapter_chat():
    """_RouterLLMAdapter.chat() delegates to ModelRouter."""
    reset_llm_client()
    with patch("app.core.database.AsyncSessionLocal") as mock_session:
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_db
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = AsyncMock()
        mock_db.execute.return_value = mock_result

        client = await get_llm_client()

        mock_router = AsyncMock()
        mock_router.chat.return_value = {
            "content": "Hello!", "model": "test", "usage": None, "provider": "test",
        }
        client._router = mock_router

        result = await client.chat([{"role": "user", "content": "hi"}])
        assert result == "Hello!"
        mock_router.chat.assert_called_once()


@pytest.mark.asyncio
async def test_router_adapter_embed():
    """_RouterLLMAdapter.embed() delegates to ModelRouter."""
    reset_llm_client()
    with patch("app.core.database.AsyncSessionLocal") as mock_session:
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_db
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = AsyncMock()
        mock_db.execute.return_value = mock_result

        client = await get_llm_client()

        mock_router = AsyncMock()
        mock_router.embed.return_value = [[0.1, 0.2, 0.3]]
        client._router = mock_router

        result = await client.embed("test text")
        assert result == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_router_adapter_chat_failure():
    """When router chat fails, adapter returns fallback message."""
    reset_llm_client()
    with patch("app.core.database.AsyncSessionLocal") as mock_session:
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_db
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = AsyncMock()
        mock_db.execute.return_value = mock_result

        client = await get_llm_client()

        mock_router = AsyncMock()
        mock_router.chat.side_effect = RuntimeError("API down")
        client._router = mock_router

        result = await client.chat([{"role": "user", "content": "hi"}])
        assert result == "[LLM unavailable]"


@pytest.mark.asyncio
async def test_router_adapter_embed_failure():
    """When router embed fails, adapter returns empty list."""
    reset_llm_client()
    with patch("app.core.database.AsyncSessionLocal") as mock_session:
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_db
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = AsyncMock()
        mock_db.execute.return_value = mock_result

        client = await get_llm_client()

        mock_router = AsyncMock()
        mock_router.embed.side_effect = RuntimeError("embed down")
        client._router = mock_router

        result = await client.embed("test")
        assert result == []


def test_reset_llm_client():
    """reset_llm_client() clears the cached adapter."""
    reset_llm_client()
    from app.llm import _router_adapter
    assert _router_adapter is None
