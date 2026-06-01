"""JD generation tool."""

from __future__ import annotations

import logging
from typing import Any

from app.llm import get_llm_client

logger = logging.getLogger(__name__)


async def _handle_generate_jd(title="", requirements="", preferences=""):
    llm = get_llm_client()
    prompt = f"请为以下职位生成完整的职位描述（JD）。\n\n职位名称：{title}\n要求：{requirements}\n"
    if preferences:
        prompt += f"其他偏好：{preferences}\n"
    prompt += "\n输出格式：\n## 职位名称\n### 岗位职责\n### 任职要求\n### 加分项\n### 薪资范围"
    try:
        result = await llm.chat([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=2048)
        return {"title": title, "jd": result}
    except Exception as e:
        logger.warning("JD generation failed: %s", e)
        return {"title": title, "jd": f"## {title}\n\n{requirements}", "fallback": True}


tools = [
    {"type": "function", "function": {"name": "generate_jd", "description": "生成职位描述（JD）。基于职位名称和要求，自动生成完整的岗位描述。", "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "职位名称"}, "requirements": {"type": "string", "description": "职位要求/描述"}, "preferences": {"type": "string", "description": "其他偏好（可选）"}}, "required": ["title", "requirements"]}}},
]

handlers = {"generate_jd": _handle_generate_jd}
