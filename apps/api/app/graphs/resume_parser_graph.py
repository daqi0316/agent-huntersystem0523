"""ResumeParser StateGraph — 7-step 简历解析工作流。

不做 subgraph 薄包装，展开为 7 个独立节点：
  validate → parse → confidence → quality → risk → dedup → output
  每步之后创建 checkpoint，支持 interrupt 和恢复。
"""

from __future__ import annotations

import logging
import re
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
    duplicate_id: str | None
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
    """Pass through + cross-validate quality score from parse step.

    parse 步骤已用 _compute_quality 计算 0-100 分；这里做交叉校验：
    - 若 parse 给了分但核心联系信息缺失 → 降分
    - 若 parse 完全没给分 → 兜底
    """
    parsed = state.get("parsed_data") or {}
    basic = parsed.get("basic_info", {})

    score = state.get("quality_score") or parsed.get("quality_score") or 0

    core_present = sum(1 for k in ("name", "email", "phone") if basic.get(k))
    if core_present == 0 and score > 30:
        score = max(score - 20, 0)
    elif core_present == 1 and score > 50:
        score = max(score - 10, 0)

    score = max(0, min(100, score))
    return {"quality_score": score, "current_step": "quality"}


def _step_risk(state: ResumeParserState) -> dict:
    """Enrich red_flags with additional heuristics beyond what parse step found.

    parse 步骤只检测 "inexperienced"；这里补充：
    - missing_email (high): 无法联系
    - missing_phone (medium): 联系渠道缺失
    - skill_overflow (low): 技能 > 20 项可疑
    - no_experience_data (info): 工作年限缺失
    """
    parsed = state.get("parsed_data") or {}
    basic = parsed.get("basic_info", {})
    skills = parsed.get("skills") or []
    existing = list(state.get("red_flags") or [])
    seen = {f.get("type") for f in existing}

    def _add(flag_type: str, severity: str, description: str) -> None:
        if flag_type not in seen:
            existing.append({"type": flag_type, "severity": severity, "description": description})
            seen.add(flag_type)

    if not basic.get("email"):
        _add("missing_email", "high", "简历中未提取到邮箱，无法联系候选人")
    if not basic.get("phone"):
        _add("missing_phone", "medium", "未提取到联系电话")
    if len(skills) > 20:
        _add("skill_overflow", "low", f"技能数量异常多（{len(skills)}项），可能为模板填充")
    if basic.get("years_of_experience") is None:
        _add("no_experience_data", "info", "未提取到工作年限信息")

    return {"red_flags": existing, "current_step": "risk"}


async def _step_dedup(state: ResumeParserState) -> dict:
    """Check DB for existing candidate by email (re-extract from raw content if masked).

    parse 步骤把 email 写进 parsed_data 时已 mask_pii，所以这里从 state["content"]
    重新用正则提取 raw email，再查 DB。同时比对 raw + 两种 mask 形式以兼容历史数据。
    """
    content = state.get("content", "")
    parsed = state.get("parsed_data") or {}
    parsed_email = parsed.get("basic_info", {}).get("email", "")

    raw_email = ""
    if parsed_email and "*" not in parsed_email and "@" in parsed_email:
        raw_email = parsed_email
    else:
        match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", content)
        if match:
            raw_email = match.group(0)

    if not raw_email:
        return {"is_duplicate": False, "duplicate_id": None, "current_step": "dedup"}

    is_duplicate = False
    duplicate_id: str | None = None

    try:
        from sqlalchemy import or_, select
        from app.agents.pii_filter import mask_pii
        from app.core.database import AsyncSessionLocal
        from app.models.candidate import Candidate

        async with AsyncSessionLocal() as db:
            masked = mask_pii(raw_email)
            stmt = (
                select(Candidate)
                .where(or_(Candidate.email == raw_email, Candidate.email == masked))
                .limit(1)
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                is_duplicate = True
                duplicate_id = str(existing.id)
    except Exception as e:
        logger.warning("Dedup check failed (DB unavailable or no candidate table): %s", e)

    return {
        "is_duplicate": is_duplicate,
        "duplicate_id": duplicate_id,
        "current_step": "dedup",
    }


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
    builder.add_node("confidence_check", _step_confidence)
    builder.add_node("quality", _step_quality)
    builder.add_node("risk", _step_risk)
    builder.add_node("dedup", _step_dedup)
    builder.add_node("output", _step_output)

    builder.set_entry_point("validate")

    builder.add_edge("validate", "parse")
    builder.add_edge("parse", "confidence_check")
    builder.add_edge("quality", "risk")
    builder.add_edge("risk", "dedup")
    builder.add_edge("dedup", "output")
    builder.add_edge("output", END)

    builder.add_conditional_edges(
        "confidence_check",
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
