import asyncio

from app.agentops.core.context import AgentOpsContext, clear_context, get_context, use_context


def test_use_context_sets_and_restores_context():
    clear_context()
    context = AgentOpsContext(trace_id="trace-1", user_id="user-1")

    with use_context(context):
        assert get_context() == context

    assert get_context() is None


def test_child_context_sets_parent_span_id():
    parent = AgentOpsContext(trace_id="trace-1", span_id="span-parent")

    child = parent.child(span_id="span-child")

    assert child.trace_id == "trace-1"
    assert child.span_id == "span-child"
    assert child.parent_span_id == "span-parent"


async def test_context_propagates_across_async_tasks():
    clear_context()
    context = AgentOpsContext(trace_id="trace-async", session_id="session-1")

    async def read_context():
        await asyncio.sleep(0)
        return get_context()

    with use_context(context):
        result = await read_context()

    assert result == context
