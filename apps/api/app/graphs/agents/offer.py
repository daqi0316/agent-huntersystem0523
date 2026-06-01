"""Offer subgraph — 薪酬谈判 Agent。"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import OfferSubState
from app.agents.registry import AgentRegistry


async def step_analyze(state: OfferSubState) -> dict:
    agent = AgentRegistry.resolve("offering")
    if not agent:
        return {"error": "offering agent not found", "current_step": "analyze"}
    result = await agent.run({
        "candidate_id": state.get("candidate_id", ""),
        "job_id": state.get("job_id", ""),
    })
    analysis = result.get("result") if isinstance(result, dict) else None
    return {
        "salary_analysis": analysis,
        "offer_created": False,
        "current_step": "analyze",
        "error": None,
    }


def create_offer_subgraph():
    builder = StateGraph(OfferSubState)
    builder.add_node("analyze", step_analyze)
    builder.set_entry_point("analyze")
    builder.add_edge("analyze", END)
    return builder.compile(checkpointer=MemorySaver())
