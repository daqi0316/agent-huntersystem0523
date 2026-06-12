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
    @patch("tavily.TavilyClient")
    async def test_success(self, mock_tavily_cls):
        mock_tavily = Mock()
        mock_tavily_cls.return_value = mock_tavily
        mock_tavily.search.return_value = {
            "answer": "This is the direct answer",
            "results": [
                {"title": "Result One", "content": "This is the first result snippet", "url": "https://example.com/1"},
                {"title": "Result Two", "content": "Second result description", "url": "https://example.com/2"},
            ],
        }

        results = await _web_search("test query")
        assert len(results) == 1
        assert "Result One" in results[0]["answer"]

    @patch("tavily.TavilyClient")
    async def test_max_results(self, mock_tavily_cls):
        mock_tavily = Mock()
        mock_tavily_cls.return_value = mock_tavily
        mock_tavily.search.return_value = {
            "answer": "Answer",
            "results": [
                {"title": "R1", "content": "C1", "url": "https://example.com/1"},
            ],
        }

        results = await _web_search("test", max_results=1)
        assert len(results) == 1

    @patch("tavily.TavilyClient")
    async def test_empty_results(self, mock_tavily_cls):
        mock_tavily = Mock()
        mock_tavily_cls.return_value = mock_tavily
        mock_tavily.search.return_value = {"answer": "", "results": []}

        results = await _web_search("nothing")
        assert results == [{"info": "未找到相关结果，请尝试其他关键词。"}]

    @patch("tavily.TavilyClient")
    async def test_http_error(self, mock_tavily_cls):
        mock_tavily = Mock()
        mock_tavily_cls.return_value = mock_tavily
        mock_tavily.search.side_effect = Exception("network error")

        results = await _web_search("fail")
        assert "error" in results[0]


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
