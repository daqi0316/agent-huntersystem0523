"""Orchestrator StateGraph — 主编排图。

每个 node 直接调用现有 Agent.run()，不做 subgraph 薄包装。
interrupt 触发后走现有 HumanLoop（ApprovalService）。
"""

from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.router_agent import RouterAgent

logger = logging.getLogger(__name__)


class OrchestratorState(TypedDict):
    task_id: str
    user_id: str
    job_id: str
    intent: str
    input_text: str
    agent_result: dict | None
    error: str | None
    status: str


_INTENT_TO_NODE = {
    "resume_parser": "execute_resume_parser",
    "screening": "execute_screening",
    "interview": "execute_interview",
    "sourcing": "execute_sourcing",
    "jd_generation": "execute_sourcing",
    "candidate_search": "execute_sourcing",
    "offering": "execute_offering",
    "onboarding": "execute_onboarding",
    "analytics": "execute_analytics",
    "report": "execute_analytics",
    "knowledge_query": "end",
    "orchestrator": "end",
    "chat": "end",
    "settings": "end",
}


def _get_agent(agent_type: str):
    from app.agents.registry import AgentRegistry
    return AgentRegistry.resolve(agent_type)


async def _intent_recognition(state: OrchestratorState) -> dict:
    text = state.get("input_text", "")
    try:
        from app.agents.bootstrap import get_router
        router = get_router()
        intent = await router.classify({"text": text})
    except Exception as e:
        logger.warning("Router classify failed (%s), falling back to 'chat'", e)
        intent = "chat"
    return {"intent": intent, "status": "running"}


async def _execute_agent(state: OrchestratorState, agent_type: str) -> dict:
    agent = _get_agent(agent_type)
    if not agent:
        return {"error": f"Agent '{agent_type}' not found", "status": "failed"}

    try:
        result = await agent.run({
            "user_id": state.get("user_id", ""),
            "job_id": state.get("job_id", ""),
            "input_text": state.get("input_text", ""),
        })
        return {"agent_result": result, "status": "completed"}
    except Exception as e:
        logger.error("Agent %s failed: %s", agent_type, e)
        return {"error": str(e), "status": "failed"}


async def execute_resume_parser(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "resume_parser")


async def execute_screening(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "screening")


async def execute_interview(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "interview")


async def execute_sourcing(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "sourcing")


async def execute_offering(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "offering")


async def execute_onboarding(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "onboarding")


async def execute_analytics(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "analytics")


def _decide_route(state: OrchestratorState) -> str:
    intent = state.get("intent", "")
    return _INTENT_TO_NODE.get(intent, "end")


def create_orchestrator_graph(checkpointer=None):
    builder = StateGraph(OrchestratorState)

    builder.add_node("intent_recognition", _intent_recognition)
    builder.add_node("execute_resume_parser", execute_resume_parser)
    builder.add_node("execute_screening", execute_screening)
    builder.add_node("execute_interview", execute_interview)
    builder.add_node("execute_sourcing", execute_sourcing)
    builder.add_node("execute_offering", execute_offering)
    builder.add_node("execute_onboarding", execute_onboarding)
    builder.add_node("execute_analytics", execute_analytics)

    builder.set_entry_point("intent_recognition")

    builder.add_conditional_edges(
        "intent_recognition",
        _decide_route,
        {
            "execute_resume_parser": "execute_resume_parser",
            "execute_screening": "execute_screening",
            "execute_interview": "execute_interview",
            "execute_sourcing": "execute_sourcing",
            "execute_offering": "execute_offering",
            "execute_onboarding": "execute_onboarding",
            "execute_analytics": "execute_analytics",
            "end": END,
        },
    )

    for node in [
        "execute_resume_parser", "execute_screening", "execute_interview",
        "execute_sourcing", "execute_offering", "execute_onboarding", "execute_analytics",
    ]:
        builder.add_edge(node, END)

    return builder.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=[
            "execute_resume_parser", "execute_screening", "execute_interview",
            "execute_sourcing", "execute_offering", "execute_onboarding", "execute_analytics",
        ],
    )
