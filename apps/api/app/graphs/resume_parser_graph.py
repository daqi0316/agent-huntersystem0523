"""ResumeParser StateGraph — 7-step 简历解析工作流。

不做 subgraph 薄包装，展开为 7 个独立节点：
  validate → parse → confidence → quality → risk → dedup → output
  每步之后创建 checkpoint，支持 interrupt 和恢复。
"""

from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import NodeInterrupt

logger = logging.getLogger(__name__)


class ResumeParserState(TypedDict):
    content: str
    file_url: str
    target_job_id: str
    current_step: str
    parsed_data: dict | None
    confidence: float
    quality_score: int
    red_flags: list[dict]
    is_duplicate: bool
    needs_human_review: bool
    result: dict | None
    error: str | None


def _step_validate(state: ResumeParserState) -> dict:
    content = state.get("content", "")
    file_url = state.get("file_url", "")
    if not content and not file_url:
        return {"error": "缺少简历内容或文件", "current_step": "validate"}
    return {"current_step": "validate", "error": None}


async def _step_parse(state: ResumeParserState) -> dict:
    from app.tools.resume_parser import _handle_parse_resume

    try:
        result = await _handle_parse_resume(
            content=state.get("content", ""),
            file_url=state.get("file_url", ""),
            target_job_id=state.get("target_job_id", ""),
        )
    except Exception as e:
        logger.warning("Parse step failed: %s", e)
        return {"error": str(e), "current_step": "parse"}

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


def _step_confidence(state: ResumeParserState) -> dict:
    confidence = state.get("confidence", 0)
    if confidence < 0.6:
        return {
            "needs_human_review": True,
            "current_step": "confidence",
        }
    elif confidence < 0.8:
        return {
            "needs_human_review": False,
            "current_step": "confidence",
        }
    return {
        "needs_human_review": False,
        "current_step": "confidence",
    }


def _step_quality(state: ResumeParserState) -> dict:
    return {"current_step": "quality"}


def _step_risk(state: ResumeParserState) -> dict:
    return {"current_step": "risk"}


def _step_dedup(state: ResumeParserState) -> dict:
    return {"current_step": "dedup"}


def _step_output(state: ResumeParserState) -> dict:
    parsed = state.get("parsed_data") or {}
    confidence = state.get("confidence", 0)
    quality_score = state.get("quality_score", 0)
    red_flags = state.get("red_flags", [])
    is_duplicate = state.get("is_duplicate", False)
    needs_review = state.get("needs_human_review", False)

    if confidence < 0.6:
        status_text = "需人工复核"
    elif confidence < 0.8:
        status_text = "部分字段待确认"
    else:
        status_text = "解析完成"

    result = {
        "parsed_data": parsed,
        "confidence": confidence,
        "quality_score": quality_score,
        "red_flags": red_flags,
        "is_duplicate": is_duplicate,
        "needs_human_review": needs_review,
        "status": status_text,
    }
    return {"result": result, "current_step": "output"}


def _decide_after_confidence(state: ResumeParserState) -> str:
    if state.get("error"):
        return "error"
    if state.get("needs_human_review"):
        return "interrupt"
    return "continue"


def _decide_after_error(state: ResumeParserState) -> str:
    return "end"


def create_resume_parser_graph(checkpointer=None):
    builder = StateGraph(ResumeParserState)

    builder.add_node("validate", _step_validate)
    builder.add_node("parse", _step_parse)
    builder.add_node("confidence", _step_confidence)
    builder.add_node("quality", _step_quality)
    builder.add_node("risk", _step_risk)
    builder.add_node("dedup", _step_dedup)
    builder.add_node("output", _step_output)

    builder.set_entry_point("validate")

    builder.add_edge("validate", "parse")
    builder.add_edge("parse", "confidence")
    builder.add_edge("quality", "risk")
    builder.add_edge("risk", "dedup")
    builder.add_edge("dedup", "output")
    builder.add_edge("output", END)

    builder.add_conditional_edges(
        "confidence",
        _decide_after_confidence,
        {
            "continue": "quality",
            "interrupt": "quality",
            "error": END,
        },
    )

    return builder.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=[],
    )
