from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.llm.vllm_client import VLLMClient


class TestVLLMClientChat:
    @patch("app.llm.vllm_client.AsyncOpenAI")
    async def test_raise_on_error(self, mock_openai):
        mock_instance = AsyncMock()
        mock_openai.return_value = mock_instance
        mock_instance.chat.completions.create.side_effect = Exception("API down")

        client = VLLMClient()
        with pytest.raises(Exception):
            await client.chat([{"role": "user", "content": "hi"}], raise_on_error=True)


class TestWebSearchMissingTitle:
    @patch("tavily.TavilyClient")
    async def test_skip_missing_title_element(self, mock_client_cls):
        from app.skills.web_search.skill import _web_search

        mock_client = Mock()
        mock_client_cls.return_value = mock_client
        # Simulate Tavily result where first source has no title
        mock_client.search.return_value = {
            "answer": "",
            "results": [
                {"title": "", "content": "Content without title"},  # should be skipped
                {"title": "Title 2", "content": "Content 2"},
            ],
        }

        results = await _web_search("test")
        assert len(results) == 1
        assert "Title 2" in results[0]["answer"]
