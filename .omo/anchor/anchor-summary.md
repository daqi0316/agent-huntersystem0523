# Anchored Summary

## SHORT VERSION
**Phase V PR-V.1 + PR-V.2 + PR-V.3 shipped** (3 of 4 PRs). PR-V.1: `orchestrator_graph.py` multi-stage DAG support — `7bf5d57`. PR-V.2: `human_loop /resume` migrated to `graph.update_state` + `ainvoke(None, config)` with legacy fallback — `c2119e3`. PR-V.3: `chat_with_tools` Step 1 migrated from `OrchestratorAgent().run()/route_single()` to `create_orchestrator_graph().ainvoke()` + `_adapt_graph_result_to_legacy()` — `6f4898c`. Combined: 70 new tests, 180/180 regression across adapter + orchestrator_flow + test_orchestrator + test_graphs + human_loop + migration suites. Only PR-V.4 (delete legacy files) remains.

## WHAT WE ARE BUILDING
AI Recruitment System — FastAPI + Next.js 14 monorepo with 6 Agent patterns (Pipeline, Router, Orchestrator with DAG, Aggregator, GenEvalLoop, HumanLoop), dual LLM support, PostgreSQL/Redis/Qdrant storage, and RAG-powered candidate screening.

Phase V is the sunset-migration plan: retire legacy `orchestrator.py` + `OrchestratorSession` in favor of the new LangGraph-based `orchestrator_graph.py` (file added in commit `a8b0212`). PR-V.1 = multi-stage DAG, PR-V.2 = resume endpoint migration, PR-V.3 = chat_with_tools Step 1 migration. PR-V.4 only remaining (delete legacy files + final test cleanup).

## CURRENT STATE
PR-V.1 + PR-V.2 + PR-V.3 complete and committed. The full flow is now:

1. Client sends a message → `chat_with_tools` is called (PR-V.3 migrated Step 1 to graph.ainvoke)
2. **chat_with_tools Step 1 (PR-V.3)**: `create_orchestrator_graph(checkpointer=None, with_interrupt=False).ainvoke(make_initial_orchestrator_state(user_id, input_text=msg))` → state → `_adapt_graph_result_to_legacy(state)` → legacy-format result for downstream `_build_approval_response()` + `_summarize_orch_result()`
3. **chat_with_tools fallback** (PR-V.3): if `graph.ainvoke` raises → fall through to LLM tool-calling loop
4. For multi-stage runs that pause: `_run_sub_task` calls `HumanLoopAgent.create_proposal(..., thread_id=<graph thread_id>)`, which writes Redis index `appr:graph_thread:{approval_id} → thread_id` (24h TTL)
5. Client reviews + approves via `POST /human-loop/approve`
6. Client calls `POST /human-loop/resume` with `approval_id`:
   - **Graph path (PR-V.2)**: read Redis index → `graph.get_state` → mark awaiting entry approved → `graph.update_state` → `graph.ainvoke(None, config)` → continue from paused level
   - **Legacy fallback (PR-V.4 deletes)**: `OrchestratorSession.find_by_approval_id` → recreate `OrchestratorAgent` → re-execute remaining levels
7. Migration script `migrate_legacy_orchestrator_sessions()` runs at lifespan startup, SCANs `orch:session:*` keys, logs orphans

## KEY METRICS
- PR-V.1 tests: 52/52 pass
- PR-V.2 tests: 17 new (6 graph path + 11 migration script), all pass
- PR-V.3 tests: 4 rewritten + 1 new (test_graph_ainvoke_passes_input_text_and_user_id) + 2 deleted (deprecated xfail); all pass
- Combined regression: 180/180 pass (test_graph_adapter 7 + TestChatWithToolsOrchestratorFlow 5 + test_orchestrator 64 + test_graphs/ 64 + test_human_loop_api 29 + test_human_loop_resume_migration 11)
- Commits: `7bf5d57` (PR-V.1) + `c2119e3` (PR-V.2) + `6f4898c` (PR-V.3)
- New files: `app/services/orchestrator_session_migration.py`, `tests/test_human_loop_resume_migration.py`
- Modified files: PR-V.1 (4) + PR-V.2 (4) + PR-V.3 (3: agent_service.py + 2 test files)
- Branch: `main`, 31 commits ahead of `origin/main`, 1 untracked file `AI招聘Agent内置命令规划.md` (unrelated)

## RECENT CHANGES
- **PR-V.3 agent_service Step 1 migration** (`6f4898c`):
  - `apps/api/app/services/agent_service.py:578-621` — replaced `OrchestratorAgent().run()/route_single()` block with `create_orchestrator_graph(checkpointer=None, with_interrupt=False).ainvoke(make_initial_orchestrator_state(user_id, input_text=msg))` + `_adapt_graph_result_to_legacy(state)`. Design: `checkpointer=None` (per-request in-memory, no Redis persistence; PR-V.2's `/resume` uses separate Redis-backed graph via `app/api/orchestrator._get_graph()`); `with_interrupt=False` (one-shot path, no pause/resume; awaiting_approval still works via state mutation `paused_at_level` + `status`)
  - `tests/test_agent_service.py::TestChatWithToolsOrchestratorFlow` — 4 tests rewritten to mock the new graph factory + adapter (using `GRAPH_FACTORY_PATH = "app.graphs.orchestrator_graph.create_orchestrator_graph"` to patch the source module for function-local imports, mirroring legacy `ORCH_CLASS_PATH` pattern). `ORCH_CLASS_PATH` + `_make_orch_mock` helper removed (no longer used)
  - New test `test_graph_ainvoke_passes_input_text_and_user_id` — verifies `create_orchestrator_graph` called with `(checkpointer=None, with_interrupt=False)` and ainvoke receives state with `input_text=last_user_msg`
  - `tests/test_orchestrator.py` — deleted 2 xfail tests (`test_execute_sub_task_interview_awaits_approval` + `test_run_with_awaiting_approval`) targeting deprecated `OrchestratorAgent` methods that PR-V.4 deletes. Coverage preserved in `test_orchestrator_graph_multistage.py` from PR-V.1
- **PR-V.2 resume migration** (`c2119e3`):
  - `HumanLoopAgent.create_proposal(..., thread_id=None)` — when `thread_id` provided, writes Redis index `appr:graph_thread:{approval_id} → thread_id` (24h TTL)
  - `orchestrator_graph._run_sub_task` now accepts `thread_id` kwarg, passes to `create_proposal`
  - `orchestrator_graph._execute_level(state, config=None)` — extracts `thread_id` from `RunnableConfig["configurable"]["thread_id"]`, forwards to `_run_sub_task`
  - `_run_sub_task` fixtures in `test_orchestrator_graph_multistage.py` updated to accept `thread_id=None` kwarg (9 occurrences, `replaceAll`)
  - `app/api/human_loop.py /resume` rewritten with:
    - `_resolve_graph_thread_id(approval_id)` — Redis lookup
    - `_resume_via_graph(approval_id, thread_id)` — graph state path
    - `_resume_legacy(approval_id)` — fallback to `OrchestratorSession`
  - `app/services/orchestrator_session_migration.py` — `migrate_legacy_orchestrator_sessions()` SCANs `orch:session:*`, classifies resumable vs orphaned, logs warnings
  - `app/main.py` lifespan calls migration after agent init
  - `tests/test_human_loop_api.py`: added `TestResumeViaGraph` class (6 tests) — success, multi-approval continuation, missing state, not paused, approval not in state, invoke failure
  - `tests/test_human_loop_resume_migration.py`: 11 new tests for migration script
- **PR-V.1 multi-stage DAG** (`7bf5d57`, previous): Extended `OrchestratorState` with 7 fields, added 3 nodes, conditional edge, checkpointer state preservation

## NEXT STEPS (Actionable)
1. **PR-V.4** — Test rewrites + `__init__.py` cleanup (1 day per phase-v.md). Delete `app/agents/orchestrator_agent.py` + `app/agents/orchestrator_session.py` after `grep -r "OrchestratorAgent\|OrchestratorSession" apps/api/app/` returns 0. Rewrite remaining `test_orchestrator.py` tests (846-line file) to test the new graph path. Remove 4 re-exports from `app/agents/__init__.py` (`OrchestratorAgent`/`get_orchestrator`/`PipelineOrchestrator`/`SequentialOrchestrator`).
2. Optional: clean up remaining 3 `pytestmark` warnings in `test_mcp_servers_api.py` (cosmetic, pre-existing)

## CRITICAL CONTEXT
- `OrchestratorState` (in `orchestrator_graph.py`) is NOT `TaskState` (in `app/core/state.py`) — different TypedDicts, different fields, different factories
- `make_initial_orchestrator_state()` is the correct factory for `OrchestratorState`; do NOT use `make_initial_task_state()` for the new graph
- Multi-stage pause is state-based (`paused_at_level` + `status="awaiting_approval"`), NOT via LangGraph `interrupt_before` — deliberate choice to keep single-intent's native interrupt untouched
- Test pattern: `graph = create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=False)`
- `RouterAgent.is_multi_intent(text)` keywords: `["然后", "并且", "同时", "之后", "接着", "先", "再", "首先", "最后", "并", "and", "then", "also", "after", "meanwhile", "next"]`
- `OrchestratorAgent._needs_human_review(result, task_type)` is a static method — must be patched in tests
- **PR-V.2 contract**: approval_id → thread_id via Redis index `appr:graph_thread:{approval_id}` (24h TTL). `graph.update_state(config, {"paused_at_level": None, "status": "running", "results": [...approved entry...]})` then `graph.ainvoke(None, config=config)` resumes from paused level
- **Migration script is read-only**: never deletes keys, only logs. Legacy `OrchestratorSession` keys age out via 24h TTL or drain manually before PR-V.4
- **Test gotcha**: mock patches on `app.core.redis.get_redis` require LOCAL imports inside the function (not module-level) — see how `_resolve_graph_thread_id` and `migrate_legacy_orchestrator_sessions` import `get_redis` inside the function
- **Test gotcha**: `_run_sub_task` signature changed in PR-V.2 — `fake_run_sub_task` test fixtures must accept `thread_id=None` kwarg
- **Test gotcha (PR-V.3)**: function-local imports in `chat_with_tools` (`from app.graphs.orchestrator_graph import ...`) require patching the SOURCE module path, e.g. `patch("app.graphs.orchestrator_graph.create_orchestrator_graph")` — NOT `patch("app.services.agent_service.create_orchestrator_graph")` (the latter fails with AttributeError because the name is not bound at module level). Mirrors the legacy `ORCH_CLASS_PATH = "app.agents.orchestrator_agent.OrchestratorAgent"` pattern.
- Background explore/librarian agents FAIL with "Insufficient balance" — rely on direct tool reads
- Python: `apps/api/.venv/bin/python` (3.14.3) — no system `python` in PATH
- LSP `basedpyright` not installed — fallback to `pytest` + `ast.parse` for verification

## COMMAND HISTORY (this session)
- PR-V.1: `pytest apps/api/tests/test_graphs/test_orchestrator_graph_multistage.py --tb=short` — 52/52 pass
- PR-V.1 regression: `pytest apps/api/tests/test_graphs/ apps/api/tests/test_graph_adapter.py --tb=short` — 71/71 pass
- PR-V.1 commit: `7bf5d57` (feat(graph): PR-V.1 multi-stage DAG support for orchestrator_graph)
- PR-V.1 docs commit: `89146cd` (docs(plans): mark Phase V PR-V.1 complete in plan + anchor)
- PR-V.2 verification: `python -c "from app.graphs.orchestrator_graph import _run_sub_task, _execute_level; import inspect; print(inspect.signature(_run_sub_task))"` — confirms new signatures
- PR-V.2 fixture fix: `replaceAll` updated 9 `fake_run_sub_task` to accept `thread_id=None`
- PR-V.2 test runs:
  - `pytest apps/api/tests/test_human_loop_api.py` — 29/29 pass (23 legacy + 6 graph path)
  - `pytest apps/api/tests/test_human_loop_resume_migration.py` — 11/11 pass (after local-import fix for `get_redis`)
  - `pytest apps/api/tests/test_human_loop_api.py apps/api/tests/test_human_loop_resume_migration.py apps/api/tests/test_graphs/ apps/api/tests/test_graph_adapter.py` — 111/111 pass
- PR-V.2 commit: `c2119e3` (feat(api): PR-V.2 migrate /resume to LangGraph checkpointer)
- PR-V.3 test runs:
  - `pytest apps/api/tests/test_graph_adapter.py apps/api/tests/test_agent_service.py::TestChatWithToolsOrchestratorFlow` — 12/12 pass (7 adapter + 5 orchestrator flow)
  - `pytest apps/api/tests/test_orchestrator.py` — 64/64 pass (2 deprecated xfail tests deleted)
  - `pytest apps/api/tests/test_graphs/` — 64/64 pass
  - `pytest apps/api/tests/test_human_loop_api.py apps/api/tests/test_human_loop_resume_migration.py` — 40/40 pass
  - Combined: 180/180 pass across all 6 suites
- PR-V.3 commit: `6f4898c` (feat(services): PR-V.3 migrate agent_service Step 1 to graph.ainvoke + delete 2 deprecated xfail tests)
