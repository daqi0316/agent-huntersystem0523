# Session Summary — Memory System Architecture Audit

**Date**: 2026-05-29
**Scope**: Phase 0 — Codebase context gathering for memory subsystem improvements

---

## What We Did

### Phase 0.1 — Read All Prompt Files (8 files)
- `sourcing.md`, `screening.md`, `interview.md`, `offering.md`, `onboarding.md`
- `analytics.md`, `router.md`, `orchestrator.md`
- `base.py` — auto-loads prompts from `prompts/` directory by agent name

### Phase 0.2 — Read Criticial Source Files

**Models (2):**
- `models/memory_fact.py` — MemoryFact ORM model (62 lines, JSONB object_value)
- `models/session_summary.py` — SessionSummary ORM model (40 lines, unique on user_id+session_id)

**Services (4):**
- `services/memory_fact.py` — MemoryFactService (359 lines) — 9 tool handlers, structured context injection
- `services/summary_service.py` — SummaryService (323 lines) — LLM summaries, PG+Qdrant dual persistence
- `services/knowledge.py` — KnowledgeService (206 lines) — RAG QA, hardcoded `knowledge_base` collection
- `services/qdrant_service.py` — QdrantService (181 lines) — domain wrapper for AsyncQdrantClient

**Agents (3):**
- `agents/base.py` — BaseAgent (124 lines) — auto-propmt loading, auto-registry, unified output protocol
- `agents/router_agent.py` — single-intent routing
- `graphs/orchestrator_graph.py` — orchestrator_graph — LangGraph DAG decomposition, shared_context, HIL

**Config:**
- `core/config.py` — 3 Qdrant collection configs: `resumes`, `session_summaries`, plus hardcoded `knowledge_base`

### Phase 0.3 — Cross-reference & Sourcing

**Grep results**: MemoryFactService/SummaryService/KnowledgeService imported in 27 locations across 9 files.

**Migration discovered**: `f4e8d2c1a3b6` — creates `memory_facts` table (already applied)

### Phase 0.4 — Data Flow Mapped

```
User → orchestrator_graph (LangGraph)
  ├─ MemoryFactService.get_structured_context()  ◄─ past facts
  ├─ SummaryService.get_relevant()               ◄─ past summaries
  ├─ KnowledgeService.query()                    ◄─ RAG
  ├─ DAG tasks → RouterAgent → Specialized Agents
  │   └─ Each → MemoryFactService.record_tool_result()  ◄─ write fact
  ├─ [HIL pause] paused_at_level + awaiting_approval (checkpointer)
  └─ SummaryService.generate()                   ◄─ write summary
```

### Key Discovery: `screen_resume` Missing from Orchestrator SubTask Types

During Phase 0, the bug that triggered this session was:
- `screening` exists in `_SUB_TASK_TYPES` → maps to `screening` keyword
- But `screen_resume` did NOT appear in orchestrator sub-task handling
- When orchestrator received "screen resume" input, it fell through to the LLM guess or default `screening`
- The fix: add `screen_resume` to orchestrator sub-task handling (since merged into orchestrator_graph `_SUB_TASK_TYPES`)

### Test Landscape

- 4 memory-related test files across 69 total API tests
- `test_memory_fact.py`: 24 tests
- `test_summary_service.py`: 17 tests
- `test_memory.py`, `test_shared_memory.py`: additional coverage

## Output

- `apps/api/app/memory/ARCHITECTURE.md` — comprehensive memory system architecture document

## Next

Phase 1: Add `screen_resume` to orchestrator's sub-task types and sub-task routing.
