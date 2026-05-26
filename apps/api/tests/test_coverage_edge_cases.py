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
    @patch("app.skills.web_search.skill.httpx.AsyncClient")
    async def test_skip_missing_title_element(self, mock_client_cls):
        from app.skills.web_search.skill import _web_search

        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = Mock()
        mock_resp.text = """<html><body>
<div class="result">
  <div class="result__snippet">no title here</div>
</div>
<div class="result">
  <div class="result__title"><a href="https://ex.com/2">Title 2</a></div>
  <div class="result__snippet">Snippet 2</div>
</div>
</body></html>"""
        mock_client.get.return_value = mock_resp

        results = await _web_search("test")
        assert len(results) == 1
        assert results[0]["title"] == "Title 2"
