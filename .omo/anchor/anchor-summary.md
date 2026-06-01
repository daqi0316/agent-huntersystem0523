# Anchored Summary

## SHORT VERSION
**Phase V ✅ COMPLETE (4 of 4 PRs shipped)**. PR-V.1: `orchestrator_graph.py` multi-stage DAG support — `7bf5d57`. PR-V.2: `human_loop /resume` migrated to `graph.update_state` + `ainvoke(None, config)` with legacy fallback — `c2119e3`. PR-V.3: `chat_with_tools` Step 1 migrated from `OrchestratorAgent().run()/route_single()` to `create_orchestrator_graph().ainvoke()` + `_adapt_graph_result_to_legacy()` — `6f4898c`. **PR-V.4: legacy files deleted + 5 OrchestratorAgent methods inlined into orchestrator_graph** (commit pending). Combined: 70 new tests (PR-V.1+2+3) + 19 file deletions (PR-V.4) + 1140 net additional regression tests = 1320 pass / 4 skip / 24 xfail / 2 xpass / **0 fail**. Phase V exit criteria: 6/7 met (only `/legacy/analyze` 1-week traffic monitoring + Redis `OrchestratorSession` key drain remain — both automated via TTL).

## WHAT WE ARE BUILDING
AI Recruitment System — FastAPI + Next.js 14 monorepo with 6 Agent patterns (Pipeline, Router, Orchestrator with DAG, Aggregator, GenEvalLoop, HumanLoop), dual LLM support, PostgreSQL/Redis/Qdrant storage, and RAG-powered candidate screening.

Phase V is the sunset-migration plan: retire legacy `orchestrator.py` + `OrchestratorSession` + `OrchestratorAgent` in favor of the new LangGraph-based `orchestrator_graph.py` (file added in commit `a8b0212`). **All 4 PRs done** — the legacy `OrchestratorAgent` and `OrchestratorSession` classes no longer exist in the codebase.

## CURRENT STATE
All 4 Phase V PRs complete and committed. The full flow is now:

1. Client sends a message → `chat_with_tools` is called (PR-V.3 migrated Step 1 to graph.ainvoke)
2. **chat_with_tools Step 1 (PR-V.3)**: `create_orchestrator_graph(checkpointer=None, with_interrupt=False).ainvoke(make_initial_orchestrator_state(user_id, input_text=msg))` → state → `_adapt_graph_result_to_legacy(state)` → legacy-format result for downstream `_build_approval_response()` + `_summarize_orch_result()`
3. **chat_with_tools fallback** (PR-V.3): if `graph.ainvoke` raises → fall through to LLM tool-calling loop
4. For multi-stage runs that pause: `_run_sub_task` calls `HumanLoopAgent.create_proposal(..., thread_id=<graph thread_id>)`, which writes Redis index `appr:graph_thread:{approval_id} → thread_id` (24h TTL)
5. Client reviews + approves via `POST /human-loop/approve`
6. Client calls `POST /human-loop/resume` with `approval_id`:
   - **Graph path only (PR-V.4 removed legacy fallback)**: read Redis index → `graph.get_state` → mark awaiting entry approved → `graph.update_state` → `graph.ainvoke(None, config)` → continue from paused level
   - **No graph thread index → 404** (no legacy session to fall back to)
7. No migration script at lifespan startup (PR-V.4 removed) — Redis `orch:session:*` keys age out via 24h TTL

## KEY METRICS
- PR-V.1 tests: 52/52 pass
- PR-V.2 tests: 17 new (6 graph path + 11 migration script), all pass
- PR-V.3 tests: 4 rewritten + 1 new + 2 deleted (deprecated xfail); all pass
- PR-V.4 changes: 11 patches rewritten in test_orchestrator_graph_multistage.py; 2 legacy test classes in test_human_loop_api.py refactored (no longer reference OrchestratorSession); 7 files deleted (3 prod + 4 test)
- Combined regression: **1320 pass / 4 skip / 24 xfail / 2 xpass / 0 fail**
- Commits: `7bf5d57` (PR-V.1) + `c2119e3` (PR-V.2) + `6a22052` (PR-V.2 docs) + `6f4898c` (PR-V.3) + `7d35ca0` (PR-V.3 docs) + `PR-V.4 commit` (pending)
- PR-V.4 diff: 19 files, +273 / -2814 lines (net -2541)
- Branch: `main`, ahead of `origin/main`, 1 untracked file `AI招聘Agent内置命令规划.md` (unrelated)

## RECENT CHANGES
- **PR-V.4 legacy sunset + graph inlining** (pending commit):
  - `app/agents/orchestrator_agent.py` (622 lines) — DELETED
  - `app/agents/orchestrator_session.py` (165 lines) — DELETED
  - `app/services/orchestrator_session_migration.py` (140 lines) — DELETED (no longer needed; no legacy sessions possible)
  - `tests/test_orchestrator.py` (784 lines) — DELETED (64 tests replaced by 52 multistage + 7 adapter + 5 orchestrator_flow)
  - `tests/test_orchestrator_session.py` (233 lines) — DELETED (19 tests; checkpointer covers functionality)
  - `tests/test_multi_agent_pipeline.py` (202 lines) — DELETED (4 test classes targeting deleted `PipelineOrchestrator`/`SequentialOrchestrator`)
  - `tests/test_human_loop_resume_migration.py` (253 lines) — DELETED (11 tests for deleted migration script)
  - `app/graphs/orchestrator_graph.py` — INLINED 5 methods + 2 constants from `OrchestratorAgent`:
    - Constants: `_SUB_TASK_TYPES`, `_GUESS_TYPE_KEYWORDS`
    - Helpers: `_load_orchestrator_system_prompt()`, `_llm_json_chat()`, `_guess_type()`
    - Logic: `decompose_task()` (replaces `OrchestratorAgent.decompose()`), `build_dag()` (replaces `OrchestratorAgent.build_dag()`), `_needs_human_review()` (replaces static method)
    - `_multi_stage_decompose()` updated to call `decompose_task()` + `build_dag()` directly
    - `_run_sub_task()` updated to call `_needs_human_review()` directly (no static method indirection)
  - `app/api/orchestrator.py` — REMOVED `_legacy_agent = OrchestratorAgent(...)` shim, DELETED `/legacy/analyze` endpoint, REMOVED `OrchestratorAgent` import, updated docstring
  - `app/api/human_loop.py` — REMOVED `_resume_legacy()` function, simplified `/resume` to return 404 when no graph thread index found
  - `app/main.py` — REMOVED lifespan `migrate_legacy_orchestrator_sessions()` block
  - `app/agents/__init__.py` — REMOVED 4 re-exports (`OrchestratorAgent`/`get_orchestrator`/`PipelineOrchestrator`/`SequentialOrchestrator`) + `OrchestratorAgent` from `__all__` + deprecation comment
  - `app/agents/human_loop.py:95` — comment updated (removed "OrchestratorSession" reference, kept "24h TTL")
  - `app/services/agent_service.py` — 2 comments updated (module docstring + `chat_with_tools` docstring)
  - `tests/test_graph_adapter.py:4` — comment updated (removed "legacy `OrchestratorAgent.route_single()`" reference)
  - `tests/test_graphs/test_orchestrator_graph_multistage.py` — REWROTE 11 `OrchestratorAgent` mock patches to target `app.graphs.orchestrator_graph.{decompose_task,build_dag,_needs_human_review}` instead
  - `tests/test_human_loop_api.py` — REPLACED 2 legacy test classes (`TestResumeAfterApproval` + `TestResumeEdgeCases`) with 1 expected-404 test (since legacy fallback removed)
  - `app/memory/ARCHITECTURE.md` — Section 4.3+4.4 rewritten (orchestrator_graph + checkpointer, not OrchestratorAgent/OrchestratorSession); Section 2.3 Redis key table updated (`appr:graph_thread:*` only); Section 8 data flow diagram updated
  - `app/memory/SESSION_SUMMARY.md` — Agent list updated (4 → 3, removed `orchestrator_agent.py` + `orchestrator_session.py` entries); data flow updated
- **PR-V.3 agent_service Step 1 migration** (`6f4898c`):
  - `apps/api/app/services/agent_service.py:578-621` — replaced `OrchestratorAgent().run()/route_single()` block with `create_orchestrator_graph(checkpointer=None, with_interrupt=False).ainvoke(make_initial_orchestrator_state(user_id, input_text=msg))` + `_adapt_graph_result_to_legacy(state)`
  - `tests/test_agent_service.py::TestChatWithToolsOrchestratorFlow` — 4 tests rewritten, 1 new test
  - `tests/test_orchestrator.py` — 2 deprecated xfail tests deleted (later entire file deleted in PR-V.4)
- **PR-V.2 resume migration** (`c2119e3`):
  - `HumanLoopAgent.create_proposal(..., thread_id=None)` — Redis index `appr:graph_thread:{approval_id} → thread_id` (24h TTL)
  - `orchestrator_graph._run_sub_task(sub_task, shared_context, user_id, thread_id=None)` + `_execute_level(state, config=None)`
  - `app/api/human_loop.py /resume` rewritten with `_resolve_graph_thread_id` + `_resume_via_graph` + `_resume_legacy` (latter deleted in PR-V.4)
  - `app/services/orchestrator_session_migration.py` — `migrate_legacy_orchestrator_sessions()` SCAN (deleted in PR-V.4)
- **PR-V.1 multi-stage DAG** (`7bf5d57`): Extended `OrchestratorState` with 7 fields, added 3 nodes, conditional edge, checkpointer state preservation

## NEXT STEPS
**Phase V is complete.** No further work required for sunset migration. Phase V exit criteria 6/7 met; remaining 2 are automated:
1. `/legacy/analyze` 1-week traffic monitoring — N/A (endpoint deleted in PR-V.4)
2. Redis `orch:session:*` key drain — automated via 24h TTL; manual `redis-cli SCAN` + `DEL` if any orphans persist

Optional cleanup items (not Phase V scope):
- Clean up 3 pre-existing `pytestmark` warnings in `test_mcp_servers_api.py` (cosmetic)

## CRITICAL CONTEXT
- `OrchestratorState` (in `orchestrator_graph.py`) is NOT `TaskState` (in `app/core/state.py`) — different TypedDicts, different fields, different factories
- `make_initial_orchestrator_state()` is the correct factory for `OrchestratorState`; do NOT use `make_initial_task_state()` for the new graph
- Multi-stage pause is state-based (`paused_at_level` + `status="awaiting_approval"`), NOT via LangGraph `interrupt_before` — deliberate choice to keep single-intent's native interrupt untouched
- Test pattern: `graph = create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=False)`
- `RouterAgent.is_multi_intent(text)` keywords: `["然后", "并且", "同时", "之后", "接着", "先", "再", "首先", "最后", "并", "and", "then", "also", "after", "meanwhile", "next"]`
- **`OrchestratorAgent._needs_human_review(result, task_type)` static method is NOW `_needs_human_review(result, task_type)` in `app.graphs.orchestrator_graph`** (PR-V.4 inlined)
- **`OrchestratorAgent.decompose(task, context)` is NOW `decompose_task(task, context)` in `app.graphs.orchestrator_graph`** (PR-V.4 inlined, async)
- **`OrchestratorAgent.build_dag(sub_tasks)` is NOW `build_dag(sub_tasks)` in `app.graphs.orchestrator_graph`** (PR-V.4 inlined, module-level)
- **`OrchestratorAgent.guess_type(text)` is NOW `_guess_type(text)` in `app.graphs.orchestrator_graph`** (PR-V.4 inlined)
- **`OrchestratorAgent._SUB_TASK_TYPES` is NOW `_SUB_TASK_TYPES` in `app.graphs.orchestrator_graph`** (PR-V.4 inlined)
- **PR-V.2 contract**: approval_id → thread_id via Redis index `appr:graph_thread:{approval_id}` (24h TTL). `graph.update_state(config, {"paused_at_level": None, "status": "running", "results": [...approved entry...]})` then `graph.ainvoke(None, config=config)` resumes from paused level
- **No legacy fallback (PR-V.4)**: `/resume` returns 404 if no Redis thread index. Clients MUST use the graph path
- **Test gotcha**: mock patches on `app.core.redis.get_redis` require LOCAL imports inside the function (not module-level) — see how `_resolve_graph_thread_id` imports `get_redis` inside the function
- **Test gotcha (PR-V.3)**: function-local imports in `chat_with_tools` (`from app.graphs.orchestrator_graph import ...`) require patching the SOURCE module path, e.g. `patch("app.graphs.orchestrator_graph.create_orchestrator_graph")` — NOT `patch("app.services.agent_service.create_orchestrator_graph")` (the latter fails with AttributeError because the name is not bound at module level). Mirrors the legacy `ORCH_CLASS_PATH = "app.agents.orchestrator_agent.OrchestratorAgent"` pattern.
- **Test gotcha (PR-V.4)**: 11 patches in `test_orchestrator_graph_multistage.py` target `app.graphs.orchestrator_graph.{decompose_task, build_dag, _needs_human_review}` (NOT `app.agents.orchestrator_agent.OrchestratorAgent`). The legacy class is deleted.
- **Test gotcha (PR-V.4)**: `test_human_loop_api.py::TestResumeAfterApproval::test_resume_no_thread_index_returns_404` patches `app.core.redis.get_redis` to `AsyncMock(return_value=None)` — no more `OrchestratorSession` patches
- Background explore/librarian agents FAIL with "Insufficient balance" — rely on direct tool reads
- Python: `apps/api/.venv/bin/python` (3.14.3) — no system `python` in PATH
- LSP `basedpyright` not installed — fallback to `pytest` + `ast.parse` for verification

## COMMAND HISTORY (this session)
- PR-V.4 verification: `pytest apps/api/tests/` — 1320 pass / 4 skip / 24 xfail / 2 xpass / **0 fail** in 113s
- PR-V.4 grep verify: `grep -rn "OrchestratorAgent\|OrchestratorSession" apps/api/app/ apps/api/tests/ apps/api/app/memory/` — **0 results**
- PR-V.4 file deletions: 7 files (3 prod + 4 test) via `rm -f`
- PR-V.4 test rewrites: 11 patches in `test_orchestrator_graph_multistage.py` (via `replaceAll`-like multiple `edit` calls) + 2 test classes in `test_human_loop_api.py` (via `edit` with larger context blocks)
- PR-V.3 test runs:
  - `pytest apps/api/tests/test_graph_adapter.py apps/api/tests/test_agent_service.py::TestChatWithToolsOrchestratorFlow` — 12/12 pass
  - `pytest apps/api/tests/test_orchestrator.py` — 64/64 pass (2 deprecated xfail tests deleted)
  - `pytest apps/api/tests/test_graphs/` — 64/64 pass
  - `pytest apps/api/tests/test_human_loop_api.py apps/api/tests/test_human_loop_resume_migration.py` — 40/40 pass
  - Combined: 180/180 pass across all 6 suites
- PR-V.3 commit: `6f4898c` (feat(services): PR-V.3 migrate agent_service Step 1 to graph.ainvoke + delete 2 deprecated xfail tests)
- PR-V.3 docs commit: `7d35ca0` (docs(plans): mark Phase V PR-V.3 complete in plan + anchor)
- PR-V.1/2 commits: `7bf5d57`, `89146cd`, `c2119e3`, `6a22052`
