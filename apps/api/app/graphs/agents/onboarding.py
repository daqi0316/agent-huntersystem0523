"""Onboarding subgraph — 入职跟进 Agent。"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import OnboardingSubState
from app.agents.registry import AgentRegistry


async def step_plan(state: OnboardingSubState) -> dict:
    agent = AgentRegistry.resolve("onboarding")
    if not agent:
        return {"error": "onboarding agent not found", "current_step": "plan"}
    result = await agent.run({
        "candidate_id": state.get("candidate_id", ""),
    })
    tasks = []
    if isinstance(result, dict):
        r = result.get("result", {}) if isinstance(result.get("result"), dict) else result
        tasks = r.get("tasks", []) if isinstance(r, dict) else []
    return {
        "tasks": tasks,
        "current_step": "plan",
        "error": None,
    }


def create_onboarding_subgraph():
    builder = StateGraph(OnboardingSubState)
    builder.add_node("plan", step_plan)
    builder.set_entry_point("plan")
    builder.add_edge("plan", END)
    return builder.compile(checkpointer=MemorySaver())
