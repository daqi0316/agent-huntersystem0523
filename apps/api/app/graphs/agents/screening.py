"""Screening subgraph — 筛选 Agent。"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import ScreeningSubState
from app.agents.registry import AgentRegistry


async def step_screen(state: ScreeningSubState) -> dict:
    agent = AgentRegistry.resolve("screening")
    if not agent:
        return {"error": "screening agent not found", "current_step": "screen"}
    result = await agent.run({
        "candidate_id": state.get("candidate_id", ""),
        "job_id": state.get("job_id", ""),
    })
    score = 0.0
    if isinstance(result, dict):
        r = result.get("result", {}) if isinstance(result.get("result"), dict) else {}
        score = r.get("overall_score", 0) or result.get("overall_score", 0) or 0
    return {
        "match_score": score,
        "screening_result": result.get("result") if isinstance(result, dict) else None,
        "current_step": "screen",
        "error": None,
    }


def create_screening_subgraph():
    builder = StateGraph(ScreeningSubState)
    builder.add_node("screen", step_screen)
    builder.set_entry_point("screen")
    builder.add_edge("screen", END)
    return builder.compile(checkpointer=MemorySaver())
