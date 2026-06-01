"""Interview subgraph — 面试协调 Agent。"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import InterviewSubState
from app.agents.registry import AgentRegistry


async def step_schedule(state: InterviewSubState) -> dict:
    agent = AgentRegistry.resolve("interview")
    if not agent:
        return {"error": "interview agent not found", "current_step": "schedule"}
    result = await agent.run({
        "candidate_id": state.get("candidate_id", ""),
        "job_id": state.get("job_id", ""),
    })
    scheduled = False
    if isinstance(result, dict):
        r = result.get("result", {}) if isinstance(result.get("result"), dict) else result
        scheduled = isinstance(r, dict) and r.get("interview_id") is not None
    return {
        "interview_scheduled": scheduled,
        "feedback": result.get("result") if isinstance(result, dict) else None,
        "current_step": "schedule",
        "error": None,
    }


def create_interview_subgraph():
    builder = StateGraph(InterviewSubState)
    builder.add_node("schedule", step_schedule)
    builder.set_entry_point("schedule")
    builder.add_edge("schedule", END)
    return builder.compile(checkpointer=MemorySaver())
