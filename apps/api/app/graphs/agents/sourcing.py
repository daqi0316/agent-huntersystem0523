"""Sourcing subgraph — 寻访 Agent。"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import SourcingSubState
from app.agents.registry import AgentRegistry


async def step_search(state: SourcingSubState) -> dict:
    agent = AgentRegistry.resolve("sourcing")
    if not agent:
        return {"error": "sourcing agent not found", "current_step": "search"}
    result = await agent.run({"job_id": state.get("job_id", ""), "skills": state.get("skills", [])})
    candidates = result.get("result", {}).get("candidates", []) if isinstance(result, dict) else []
    return {"candidates_found": candidates, "current_step": "search", "error": None}


def create_sourcing_subgraph():
    builder = StateGraph(SourcingSubState)
    builder.add_node("search", step_search)
    builder.set_entry_point("search")
    builder.add_edge("search", END)
    return builder.compile(checkpointer=MemorySaver())
