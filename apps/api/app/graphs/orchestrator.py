"""Orchestrator main graph — 主编排图。

挂载 6 个子图作为 Subgraph Node + SnapshotManager 快照。
interrupt_before 触发后走 HumanLoop（ApprovalService）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import TaskState, make_initial_task_state
from app.core.snapshot_manager import SnapshotManager
from app.graphs.agents.resume_parser import create_resume_parser_subgraph
from app.graphs.agents.sourcing import create_sourcing_subgraph
from app.graphs.agents.screening import create_screening_subgraph
from app.graphs.agents.interview import create_interview_subgraph
from app.graphs.agents.offer import create_offer_subgraph
from app.graphs.agents.onboarding import create_onboarding_subgraph
from app.agents.router_agent import RouterAgent

logger = logging.getLogger(__name__)

_INTENT_TO_AGENT = {
    "resume_parser": "resume_parser",
    "screening": "screening",
    "interview": "interview",
    "jd_generation": "sourcing",
    "candidate_search": "sourcing",
    "sourcing": "sourcing",
    "offering": "offer",
    "onboarding": "onboarding",
    "analytics": "analytics",
    "report": "analytics",
}


def _build_subgraphs():
    return {
        "resume_parser": create_resume_parser_subgraph(),
        "sourcing": create_sourcing_subgraph(),
        "screening": create_screening_subgraph(),
        "interview": create_interview_subgraph(),
        "offer": create_offer_subgraph(),
        "onboarding": create_onboarding_subgraph(),
    }


async def intent_recognition(state: TaskState) -> dict:
    text = state.get("input_text", "")
    router = RouterAgent()
    intent, _ = router._rule_classify(text)
    agent = _INTENT_TO_AGENT.get(intent, "chat")
    return {
        "intent": intent,
        "current_agent": agent,
        "status": "running",
    }


async def select_agent(state: TaskState) -> str:
    agent = state.get("current_agent", "")
    return agent if agent in _INTENT_TO_AGENT.values() else "end"


async def execute_subgraph(state: TaskState) -> dict:
    agent_type = state.get("current_agent", "")
    subgraphs = _build_subgraphs()
    subgraph = subgraphs.get(agent_type)
    if not subgraph:
        return {"error": f"Unknown agent: {agent_type}"}

    sub_state = _build_sub_state(agent_type, state)
    try:
        result = await subgraph.ainvoke(
            sub_state,
            config={"configurable": {"thread_id": f"{state['task_id']}_{agent_type}"}},
        )
    except Exception as e:
        logger.error("Subgraph %s failed: %s", agent_type, e)
        return {"error": str(e)}

    update = {f"{agent_type}_state": result}
    entry = {
        "agent": agent_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result_summary": str(result.get("current_step", "done"))[:100],
    }
    update["execution_history"] = [entry]
    return update


async def create_snapshot(state: TaskState) -> dict:
    mgr = SnapshotManager()
    sid = mgr.create(
        state=dict(state),
        task_id=state["task_id"],
        agent_type=state.get("current_agent", ""),
        step_name=state.get("status", ""),
        is_auto=True,
    )
    return {"snapshot_id": sid}


def _build_sub_state(agent_type: str, parent: TaskState) -> dict:
    base = {"current_step": "", "error": None}
    if agent_type == "resume_parser":
        base.update({"content": parent.get("input_text", ""), "file_url": "", "parsed_data": None, "confidence": 0,
                     "quality_score": 0, "red_flags": [], "is_duplicate": False, "needs_human_review": False})
    elif agent_type == "sourcing":
        base.update({"job_id": parent.get("job_id", ""), "skills": [], "candidates_found": []})
    elif agent_type == "screening":
        base.update({"candidate_id": "", "job_id": parent.get("job_id", ""), "match_score": 0, "screening_result": None})
    elif agent_type == "interview":
        base.update({"candidate_id": "", "job_id": parent.get("job_id", ""), "interview_scheduled": False, "feedback": None})
    elif agent_type == "offer":
        base.update({"candidate_id": "", "job_id": parent.get("job_id", ""), "salary_analysis": None, "offer_created": False})
    elif agent_type == "onboarding":
        base.update({"candidate_id": "", "employee_id": None, "tasks": []})
    return base


def create_orchestrator_graph(checkpointer=None, with_interrupt: bool = False):
    builder = StateGraph(TaskState)

    builder.add_node("intent_recognition", intent_recognition)
    builder.add_node("execute_subgraph", execute_subgraph)
    builder.add_node("create_snapshot", create_snapshot)

    builder.set_entry_point("intent_recognition")

    builder.add_conditional_edges(
        "intent_recognition",
        select_agent,
        {
            "resume_parser": "execute_subgraph",
            "sourcing": "execute_subgraph",
            "screening": "execute_subgraph",
            "interview": "execute_subgraph",
            "offer": "execute_subgraph",
            "onboarding": "execute_subgraph",
            "analytics": "execute_subgraph",
            "chat": "create_snapshot",
            "end": "create_snapshot",
        },
    )

    builder.add_edge("execute_subgraph", "create_snapshot")
    builder.add_edge("create_snapshot", END)

    kwargs = {"checkpointer": checkpointer or MemorySaver()}
    if with_interrupt:
        kwargs["interrupt_before"] = ["execute_subgraph"]

    return builder.compile(**kwargs)
