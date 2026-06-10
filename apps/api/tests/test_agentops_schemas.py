from app.agentops.core.schemas import (
    SCHEMA_VERSION,
    EventType,
    LLMGenerationEvent,
    ScoreEvent,
    ToolInvocationEvent,
    TraceEvent,
)


def test_trace_event_serializes_event_type_and_schema_version():
    event = TraceEvent(name="recruitment_agent.chat", user_id="user-1")

    data = event.to_dict()

    assert data["schema_version"] == SCHEMA_VERSION
    assert data["event_type"] == "trace.started"
    assert data["name"] == "recruitment_agent.chat"
    assert data["user_id"] == "user-1"
    assert data["event_id"]
    assert data["timestamp"]


def test_llm_generation_event_captures_model_usage_and_params():
    event = LLMGenerationEvent(
        name="generation.final_response",
        event_type=EventType.LLM_GENERATION_COMPLETED,
        provider="vllm",
        model="qwen",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        parameters={"temperature": 0.7},
    )

    data = event.to_dict()

    assert data["event_type"] == "llm.generation.completed"
    assert data["provider"] == "vllm"
    assert data["model"] == "qwen"
    assert data["total_tokens"] == 15
    assert data["parameters"] == {"temperature": 0.7}


def test_tool_and_score_events_have_domain_fields():
    tool = ToolInvocationEvent(name="tool.get_schedule", tool_name="get_schedule", success=True, retry_count=1)
    score = ScoreEvent(name="score.screening", score_name="screening_reasonability", value=4, source="human")

    assert tool.to_dict()["tool_name"] == "get_schedule"
    assert tool.to_dict()["success"] is True
    assert score.to_dict()["score_name"] == "screening_reasonability"
    assert score.to_dict()["value"] == 4
