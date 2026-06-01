"""Tests for MCP ↔ OpenAI format conversion bridge."""

import pytest
from app.mcp.bridge import mcp_tool_to_openai, mcp_content_to_text


class TestMcpToolToOpenai:
    def test_basic_conversion(self):
        mcp_tool = {
            "name": "get_weather",
            "description": "获取天气信息",
            "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}},
        }
        result = mcp_tool_to_openai(mcp_tool)
        assert result["type"] == "function"
        assert result["function"]["name"] == "get_weather"
        assert result["function"]["description"] == "获取天气信息"
        assert result["function"]["parameters"]["type"] == "object"

    def test_missing_description(self):
        mcp_tool = {
            "name": "no_desc",
            "inputSchema": {"type": "object", "properties": {}},
        }
        result = mcp_tool_to_openai(mcp_tool)
        assert result["function"]["description"] == ""

    def test_missing_input_schema(self):
        mcp_tool = {"name": "no_schema"}
        result = mcp_tool_to_openai(mcp_tool)
        assert result["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_empty_input_schema(self):
        mcp_tool = {"name": "empty", "inputSchema": {}}
        result = mcp_tool_to_openai(mcp_tool)
        assert result["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_non_dict_input_schema(self):
        mcp_tool = {"name": "bad", "inputSchema": "not a dict"}
        result = mcp_tool_to_openai(mcp_tool)
        assert result["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_missing_name(self):
        mcp_tool = {"description": "no name"}
        result = mcp_tool_to_openai(mcp_tool)
        assert result["function"]["name"] == "unknown_tool"


class TestMcpContentToText:
    def test_text_content(self):
        items = [{"type": "text", "text": "Hello world"}]
        assert mcp_content_to_text(items) == "Hello world"

    def test_multiple_texts(self):
        items = [{"type": "text", "text": "Hello"}, {"type": "text", "text": "World"}]
        assert mcp_content_to_text(items) == "Hello\nWorld"

    def test_resource_content_with_text(self):
        items = [{"type": "resource", "resource": {"text": "resource text"}}]
        assert mcp_content_to_text(items) == "resource text"

    def test_resource_content_with_blob(self):
        items = [{"type": "resource", "resource": {"blob": "base64data"}}]
        assert mcp_content_to_text(items) == "base64data"

    def test_image_content(self):
        items = [{"type": "image", "data": "...", "mimeType": "image/png"}]
        assert mcp_content_to_text(items) == "[image: image/png]"

    def test_unknown_type(self):
        items = [{"type": "audio", "data": "binary"}]
        result = mcp_content_to_text(items)
        assert "[audio:" in result

    def test_empty_content(self):
        assert mcp_content_to_text([]) == ""

    def test_missing_text_field(self):
        items = [{"type": "text"}]  # no "text" key
        result = mcp_content_to_text(items)
        assert result == ""

    def test_missing_type(self):
        items = [{"text": "hello"}]
        result = mcp_content_to_text(items)
        assert ": {'text': 'hello'}" in result  # type is empty string

    def test_mixed_content(self):
        items = [
            {"type": "text", "text": "Analysis:"},
            {"type": "resource", "resource": {"text": "Score: 85"}},
            {"type": "image", "mimeType": "image/jpeg"},
        ]
        result = mcp_content_to_text(items)
        assert "Analysis:" in result
        assert "Score: 85" in result
        assert "[image: image/jpeg]" in result
