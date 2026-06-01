"""ResumeParser subgraph — 7-step 简历解析工作流。

对应 LangGraph 设计文档 §3.2。
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import ResumeParserSubState
from app.tools.resume_parser import _handle_parse_resume


async def step_validate(state: ResumeParserSubState) -> dict:
    content = state.get("content", "")
    file_url = state.get("file_url", "")
    if not content and not file_url:
        return {"error": "缺少简历内容或文件", "current_step": "validate"}
    return {"current_step": "validate", "error": None}


async def step_parse(state: ResumeParserSubState) -> dict:
    result = await _handle_parse_resume(
        content=state.get("content", ""),
        file_url=state.get("file_url", ""),
    )
    if result.get("status") != "success":
        return {"error": result.get("error", {}).get("message", "解析失败"), "current_step": "parse"}
    data = result.get("data", {})
    return {
        "parsed_data": data,
        "confidence": data.get("confidence", 0),
        "quality_score": data.get("quality_score", 0),
        "red_flags": data.get("red_flags", []),
        "is_duplicate": data.get("is_duplicate", False),
        "current_step": "parse",
        "error": None,
    }


def step_confidence(state: ResumeParserSubState) -> dict:
    confidence = state.get("confidence", 0)
    return {
        "needs_human_review": confidence < 0.6,
        "current_step": "confidence",
    }


def step_output(state: ResumeParserSubState) -> dict:
    return {"current_step": "output"}


def _decide_after_confidence(state: ResumeParserSubState) -> str:
    if state.get("error"):
        return "error"
    return "continue"


def create_resume_parser_subgraph():
    builder = StateGraph(ResumeParserSubState)
    builder.add_node("validate", step_validate)
    builder.add_node("parse", step_parse)
    builder.add_node("confidence_check", step_confidence)
    builder.add_node("output", step_output)
    builder.set_entry_point("validate")
    builder.add_edge("validate", "parse")
    builder.add_edge("parse", "confidence_check")
    builder.add_conditional_edges("confidence_check", _decide_after_confidence, {"continue": "output", "error": END})
    builder.add_edge("output", END)
    return builder.compile(checkpointer=MemorySaver())
