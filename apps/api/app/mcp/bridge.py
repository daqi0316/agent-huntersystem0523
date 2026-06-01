"""MCP ↔ OpenAI function-calling 格式转换桥。

MCP Tool 格式:
  {name: str, description: str, inputSchema: {...}}

OpenAI function-calling 格式:
  {type: "function", function: {name, description, parameters: {...}}}
"""

from typing import Any


def mcp_tool_to_openai(mcp_tool: dict[str, Any]) -> dict[str, Any]:
    """将 MCP Tool 定义转换为 OpenAI function-calling 格式。

    Args:
        mcp_tool: MCP 工具定义 dict (name, description, inputSchema)

    Returns:
        OpenAI 格式的 tool dict
    """
    name = mcp_tool.get("name", "unknown_tool")
    description = mcp_tool.get("description", "")
    input_schema = mcp_tool.get("inputSchema", {})

    # 兼容 inputSchema 缺失的情况
    if not input_schema or not isinstance(input_schema, dict):
        input_schema = {"type": "object", "properties": {}}

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": input_schema,
        },
    }


def mcp_content_to_text(content_items: list[dict[str, Any]]) -> str:
    """将 MCP tool call 返回的 content 列表合并为纯文本。

    MCP content 条目格式:
      {type: "text", text: "..."}
      {type: "resource", resource: {text: "...", ...}}
      {type: "image", data: "...", mimeType: "..."}

    Args:
        content_items: MCP call 返回的 content 列表

    Returns:
        合并后的文本（非文本内容会标注类型）
    """
    parts: list[str] = []
    for item in content_items:
        t = item.get("type", "")
        if t == "text":
            parts.append(item.get("text", ""))
        elif t == "resource":
            resource = item.get("resource", {})
            parts.append(resource.get("text", resource.get("blob", str(resource))))
        elif t == "image":
            parts.append(f"[image: {item.get('mimeType', 'unknown')}]")
        else:
            parts.append(f"[{t}: {str(item)[:200]}]")
    return "\n".join(parts).strip()
