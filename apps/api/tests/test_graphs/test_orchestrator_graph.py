import pytest
from langgraph.checkpoint.memory import MemorySaver
from app.graphs.orchestrator import create_orchestrator_graph
from app.core.state import make_initial_task_state


@pytest.fixture
def graph():
    return create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=False)


@pytest.mark.asyncio
async def test_routes_resume_parser(graph):
    r = await graph.ainvoke(make_initial_task_state(task_id="t1", input_text="帮我解析这份简历"), config={"configurable": {"thread_id": "t1"}})
    assert r.get("intent") == "resume_parser"


@pytest.mark.asyncio
async def test_routes_screening(graph):
    r = await graph.ainvoke(make_initial_task_state(task_id="t2", input_text="帮我筛选候选人"), config={"configurable": {"thread_id": "t2"}})
    assert r.get("intent") in ("screening", "candidate_search")


@pytest.mark.asyncio
async def test_routes_interview(graph):
    r = await graph.ainvoke(make_initial_task_state(task_id="t3", input_text="安排面试"), config={"configurable": {"thread_id": "t3"}})
    assert r.get("intent") == "interview"


@pytest.mark.asyncio
async def test_creates_snapshot(graph):
    r = await graph.ainvoke(make_initial_task_state(task_id="t-snap", input_text="hello"), config={"configurable": {"thread_id": "t-snap"}})
    from app.core.snapshot_manager import SnapshotManager
    snaps = SnapshotManager().list_by_task("t-snap")
    assert len(snaps) >= 1


@pytest.mark.asyncio
async def test_checkpoint_preserved(graph):
    cfg = {"configurable": {"thread_id": "t-cp"}}
    await graph.ainvoke(make_initial_task_state(task_id="t-cp", input_text="解析这份简历"), config=cfg)
    state = graph.get_state(cfg)
    assert state is not None
    assert state.values.get("intent") is not None


@pytest.mark.asyncio
async def test_error_handled(graph):
    r = await graph.ainvoke(make_initial_task_state(task_id="t-err", input_text="xyz123unknown"), config={"configurable": {"thread_id": "t-err"}})
    assert r.get("intent") is not None


@pytest.mark.asyncio
async def test_interrupt_blocks():
    g = create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=True)
    await g.ainvoke(make_initial_task_state(task_id="t-int", input_text="解析简历"), config={"configurable": {"thread_id": "t-int"}})
    snap = g.get_state({"configurable": {"thread_id": "t-int"}})
    assert snap is not None and len(snap.next) > 0


@pytest.mark.asyncio
async def test_subgraph_execution_with_state(graph):
    r = await graph.ainvoke(make_initial_task_state(task_id="t-sub", input_text="解析这份简历"), config={"configurable": {"thread_id": "t-sub"}})
    sub = r.get("resume_parser_state") or {}
    assert "current_step" in sub or r.get("current_agent") == "resume_parser"
