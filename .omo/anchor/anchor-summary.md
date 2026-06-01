# Anchored Summary

## SHORT VERSION
**Phase V PR-V.1 shipped**: extended `apps/api/app/graphs/orchestrator_graph.py` with multi-stage DAG support (7 new state fields, 3 new nodes, conditional edge, awaiting_approval pause via checkpointer). 52 new tests in `test_orchestrator_graph_multistage.py` — all 52 pass. Full regression: 71/71 across `test_graphs/` + `test_graph_adapter.py`. Committed as `7bf5d57`.

## WHAT WE ARE BUILDING
AI Recruitment System — FastAPI + Next.js 14 monorepo with 6 Agent patterns (Pipeline, Router, Orchestrator with DAG, Aggregator, GenEvalLoop, HumanLoop), dual LLM support, PostgreSQL/Redis/Qdrant storage, and RAG-powered candidate screening.

Phase V is the sunset-migration plan: retire legacy `orchestrator.py` + `OrchestratorSession` in favor of the new LangGraph-based `orchestrator_graph.py` (file added in commit `a8b0212`). PR-V.1 = multi-stage DAG support, the most complex 2-day item.

## CURRENT STATE
PR-V.1 complete and committed. The new `orchestrator_graph` now handles:
- Multi-stage input detection (via `RouterAgent.is_multi_intent` keywords)
- Decomposition (`OrchestratorAgent.decompose` + `build_dag`)
- Parallel level execution (`asyncio.gather`)
- Awaiting_approval pause (state-based via `paused_at_level` + `status`)
- Checkpointer state preservation (all 7 multi-stage fields survive across `ainvoke` calls)
- Conditional routing (`should_continue_or_pause` → next level or END)

PR-V.2 (next): `human_loop /resume` endpoint migration — uses `graph.update_state` + `graph.ainvoke(None, config)` to consume the checkpointed state from PR-V.1.

## KEY METRICS
- PR-V.1 tests: 52/52 pass
- Regression: 71/71 pass (`test_graphs/` + `test_graph_adapter.py`)
- New state fields: 7 (`multi_stage`, `sub_tasks`, `current_level`, `levels`, `paused_at_level`, `results`, `shared_context`)
- New nodes: 3 (`multi_stage_decompose`, `execute_level`, `should_continue_or_pause`)
- New helpers: 5 (`_TYPE_TO_AGENT`, `_is_multi_stage_text`, `_normalize_sub_task_result`, `_build_sub_task_input`, `_update_shared_context`)
- Graph size: 11 nodes total (was 8 before PR-V.1)
- Commit: `7bf5d57` (1 ahead of `a8b0212`)

## RECENT CHANGES
- **PR-V.1 multi-stage DAG** (`7bf5d57`):
  - Extended `OrchestratorState` with 7 multi-stage fields
  - Added 3 new node functions + 5 helpers
  - Added `make_initial_orchestrator_state()` factory
  - Rewired `create_orchestrator_graph()` to add `multi_stage_decompose → execute_level (loop) → END` path
  - `_intent_recognition` now checks `RouterAgent.is_multi_intent` first
  - `_decide_route` routes to `multi_stage_decompose` when `multi_stage=True`
  - State-based pause (not native `interrupt_before`) — keeps single-intent's interrupt untouched
  - `if not levels: levels = [list(range(len(sub_tasks)))]` defensive rebuild handles empty-subtask edge case from `build_dag`
- **New test file `test_orchestrator_graph_multistage.py`**: 52 tests covering state helpers, multi-stage detection, decompose (with mocked `OrchestratorAgent`), level execution (parallel `asyncio.gather`), conditional routing, awaiting_approval pause, end-to-end graph flows, and checkpointer state preservation

## NEXT STEPS (Actionable)
1. **PR-V.2** — Migrate `human_loop /resume` endpoint to use `graph.update_state` + `graph.ainvoke(None, config)` (2-3 days per phase-v.md)
2. **PR-V.3** — Verify `_adapt_graph_result_to_legacy` adapter handles multi-stage results (test_graph_adapter.py already covers it; should be green)
3. **PR-V.4** — Delete legacy `orchestrator.py` + `OrchestratorSession` + 846-line `test_orchestrator.py` after all API callers migrated
4. Update `.omo/plans/phase-v.md` to mark PR-V.1 as ✅ done (1 day ahead of soft target 2026-06-08)
5. Optional: clean up remaining 3 `pytestmark` warnings in `test_mcp_servers_api.py` (cosmetic, pre-existing)

## CRITICAL CONTEXT
- `OrchestratorState` (in `orchestrator_graph.py`) is NOT `TaskState` (in `app/core/state.py`) — different TypedDicts, different fields, different factories
- `make_initial_orchestrator_state()` is the correct factory for `OrchestratorState`; do NOT use `make_initial_task_state()` for the new graph
- Multi-stage pause is state-based (`paused_at_level` + `status="awaiting_approval"`), NOT via LangGraph `interrupt_before` — this was a deliberate choice to keep single-intent's native interrupt untouched
- `with_interrupt=False` is the test fixture mode (no native interrupt for multi-stage flow); `with_interrupt=True` adds `interrupt_before` for single-intent nodes
- Test pattern: `graph = create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=False)`
- `RouterAgent.is_multi_intent(text)` keywords: `["然后", "并且", "同时", "之后", "接着", "先", "再", "首先", "最后", "并", "and", "then", "also", "after", "meanwhile", "next"]`
- `OrchestratorAgent._needs_human_review(result, task_type)` is a static method — must be patched in tests
- PR-V.1 PR-V.2 contract: PR-V.1's checkpointer must preserve `paused_at_level`, `status`, `sub_tasks`, `levels`, `results` so PR-V.2 can re-invoke with `graph.ainvoke(None, config)` after `update_state`
- Branch: `main`, 28 commits ahead of `origin/main`, 1 untracked file `AI招聘Agent内置命令规划.md` (not part of PR-V.1)
- Python: `apps/api/.venv/bin/python` (3.14.3) — no system `python` in PATH
- Background explore/librarian agents FAIL with "Insufficient balance" — rely on direct tool reads

## COMMAND HISTORY (this session)
- `pytest apps/api/tests/test_graphs/test_orchestrator_graph_multistage.py --tb=short` — 52/52 pass
- `pytest apps/api/tests/test_graphs/ apps/api/tests/test_graph_adapter.py --tb=short` — 71/71 pass
- `git add apps/api/app/graphs/orchestrator_graph.py apps/api/tests/test_graphs/test_orchestrator_graph_multistage.py`
- `git commit -m "feat(graph): PR-V.1 multi-stage DAG support for orchestrator_graph"` → `7bf5d57`
- `git log --oneline -3` — confirmed commit
- LSP `basedpyright` not installed — fallback to `pytest` + `ast.parse` for verification
- Background agents `bg_e11b7c52` + `bg_70d3f28a` both FAILED with billing error — direct tool reads substituted
