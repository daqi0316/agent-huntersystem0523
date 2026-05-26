from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.skills.web_search.skill import WebSearchSkill, _web_search

_HTML_WITH_RESULTS = """<html><body>
<div class="result">
  <div class="result__title">
    <a href="https://example.com/1">Result One</a>
  </div>
  <div class="result__snippet">This is the first result snippet</div>
</div>
<div class="result">
  <div class="result__title">
    <a href="https://example.com/2">Result Two</a>
  </div>
  <div class="result__snippet">Second result description</div>
</div>
</body></html>"""

_HTML_EMPTY = "<html><body><p>no results</p></body></html>"


class TestWebSearch:
    @patch("app.skills.web_search.skill.httpx.AsyncClient")
    async def test_success(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = Mock()
        mock_resp.text = _HTML_WITH_RESULTS
        mock_client.get.return_value = mock_resp

        results = await _web_search("test query")
        assert len(results) == 2
        assert results[0]["title"] == "Result One"
        assert results[1]["title"] == "Result Two"

    @patch("app.skills.web_search.skill.httpx.AsyncClient")
    async def test_max_results(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = Mock()
        mock_resp.text = _HTML_WITH_RESULTS
        mock_client.get.return_value = mock_resp

        results = await _web_search("test", max_results=1)
        assert len(results) == 1

    @patch("app.skills.web_search.skill.httpx.AsyncClient")
    async def test_empty_results(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = Mock()
        mock_resp.text = _HTML_EMPTY
        mock_client.get.return_value = mock_resp

        results = await _web_search("nothing")
        assert results == [{"info": "未找到相关结果，请尝试修改关键词。"}]

    @patch("app.skills.web_search.skill.httpx.AsyncClient")
    async def test_http_error(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("network error")

        with pytest.raises(Exception):
            await _web_search("fail")


class TestWebSearchSkill:
    def test_name(self):
        assert WebSearchSkill().name == "web_search"

    def test_description(self):
        assert "搜索" in WebSearchSkill().description

    def test_get_tools(self):
        tools = WebSearchSkill().get_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "web_search"

    def test_get_handlers(self):
        handlers = WebSearchSkill().get_handlers()
        assert "web_search" in handlers
