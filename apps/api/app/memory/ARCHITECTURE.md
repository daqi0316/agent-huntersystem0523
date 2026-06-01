# Memory System Architecture

> Cross-session memory, RAG knowledge base, structured fact recording, and agent orchestration state.
> Last updated: 2026-05-29

---

## 1. Overview — Three Memory Subsystems

| Subsystem | Storage | Surface | Purpose |
|---|---|---|---|
| **MemoryFact** (结构化记忆) | PostgreSQL `memory_facts` | System-prompt injection | Agent actions/decisions as structured triples (subject-verb-object) |
| **SessionSummary** (会话摘要) | PostgreSQL `session_summaries` + Qdrant `session_summaries` | Vector similarity recall | LLM-generated conversation summaries, cross-session context |
| **KnowledgeBase** (知识库) | Qdrant `knowledge_base` | RAG Q&A | Document ingestion, vector retrieval, LLM QA |

All three feed into the **orchestrator_graph** → **RouterAgent** → specialized agent chain.

---

## 2. Data Stores

### 2.1 PostgreSQL (SQLAlchemy async)

Two tables for memory:

**`memory_facts`** — `app/models/memory_fact.py` (62 lines)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | auto-generated |
| `user_id` | FK → users.id | indexed |
| `session_id` | String(255) | indexed |
| `fact_type` | String(50) | `agent_action` / `candidate_action` / `decision` |
| `subject_type` | String(50) | `candidate` / nullable |
| `subject_id` | String(255) | nullable |
| `verb` | String(50) | `searched` / `viewed` / `screened` / `passed` / `failed` / etc. |
| `object_value` | JSONB | structured payload |
| `created_at` | DateTime(tz) | server default now() |

Index: composite `(user_id, created_at)` for recent-fact queries.

**`session_summaries`** — `app/models/session_summary.py` (40 lines)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | auto-generated |
| `user_id` | FK → users.id | indexed |
| `session_id` | String(255) | indexed |
| `summary` | Text | LLM-generated summary text |
| `created_at` | DateTime(tz) | server default now() |
| `updated_at` | DateTime(tz) | onupdate |

Unique constraint: `(user_id, session_id)` — one summary per session per user.

### 2.2 Qdrant (Vector Store)

Three collections managed by two services:

| Collection Name | Config Key | Vector Size | Distance | Owner |
|---|---|---|---|---|
| `resumes` | `qdrant_collection` | auto-detected | Cosine | resume search |
| `session_summaries` | `qdrant_memory_collection` | auto-detected | Cosine | `QdrantService` (wrapper) |
| `knowledge_base` | hardcoded in `knowledge.py` | 1024 (bge-m3) | Cosine | `KnowledgeService` |

**`QdrantService`** — `app/services/qdrant_service.py` (181 lines)
- Domain-level wrapper around `AsyncQdrantClient`
- `ensure_collection()`: auto-creates with detected vector dimension
- `upsert()` / `delete()`: point CRUD
- `search()`: similarity search with threshold filter
- `scroll_by_filter()`: paginated scroll
- `count()`: point count

### 2.3 Redis (State + KV)

| Key Prefix | TTL | Owner |
|---|---|---|
| `appr:graph_thread:{approval_id}` | 24h | HumanLoopAgent (PR-V.2) |
| KV namespace (agent-level) | 1h | SharedMemory |

---

## 3. Memory Subsystems — Detailed

### 3.1 MemoryFact / MemoryFactService

**File**: `app/services/memory_fact.py` (359 lines)
**Model**: `app/models/memory_fact.py`

**Purpose**: Record agent actions and decisions as structured triples, then inject them into the agent's system prompt for cross-session recall.

**Fact types**:
- `agent_action`: searches, JD generation, dashboard views, knowledge searches
- `candidate_action`: viewed candidate, screened, scheduled interview, viewed evaluations
- `decision`: passed / failed screening

**9 tool handlers** (each converts tool result → structured facts):
`search_candidates`, `get_candidate`, `screen_resume`, `schedule_interview`, `generate_jd`, `list_jobs`, `get_dashboard_stats`, `search_knowledge`, `get_evaluations`

**Injection into agent prompts** — `get_structured_context(user_id)`:
```
【结构化记忆】
你之前处理过的候选人：
  - 张三 — 已查看 · 已初筛 (得分 85)
  - 李四 — 已安排面试 (周五 14:00)
你之前执行的操作：
  - 搜索 "Python" (找到 3 人)
```

**Constants**: `MAX_FACTS_PER_INJECTION=30`, `FACT_RECENT_DAYS=30`

### 3.2 SessionSummary / SummaryService

**File**: `app/services/summary_service.py` (323 lines)
**Model**: `app/models/session_summary.py`

**Flow**:
1. LLM generates summary from conversation messages (Chinese, ≤300 chars)
2. Embed the summary text
3. Upsert vector → Qdrant `session_summaries` collection
4. Upsert metadata → PostgreSQL `session_summaries` table

**Constants**: `DEFAULT_TOP_K=3`, `DEFAULT_SCORE_THRESHOLD=0.65`, `MAX_MEMORY_TOKENS=1500`, `MIN_MESSAGES_FOR_SUMMARY=6`

### 3.3 KnowledgeBase / KnowledgeService

**File**: `app/services/knowledge.py` (206 lines)

**Collection**: `knowledge_base` (hardcoded, no collection config)

**Operations**:
- `ensure_collection()`: create if not exists
- `ingest_document()`: chunk, embed, upload
- `search()`: vector similarity
- `query()`: search + LLM answer generation
- `list_documents()`, `delete_document()`: management

Uses `bge-m3-mlx-4bit` embedding model (1024 dim). Falls back gracefully if Qdrant is down.

---

## 4. Agent System

### 4.1 BaseAgent — `app/agents/base.py` (124 lines)

Abstract base class. Key behaviors:
1. Auto-loads system prompts from `prompts/` directory by agent name
2. Auto-registers with `AgentRegistry` via `__init_subclass__`
3. Derives `agent_type` automatically (class name minus "Agent" suffix, lowercased)
4. Unified output protocol:
   ```python
   { "agent": str, "status": str, "summary": str, "result": dict, "details": dict }
   ```
5. `output_keys` class var → exposed to Orchestrator's `shared_context`

### 4.2 RouterAgent — `app/agents/router_agent.py`

Routes single-intent tasks to specialized agents. Used by Orchestrator for multi-step decomposition and by direct API calls.

### 4.3 orchestrator_graph — `app/graphs/orchestrator_graph.py`

**Core mission**: Receive complex requests → LangGraph StateGraph decomposes into DAG sub-tasks → parallel/serial execution → aggregate results.

**Multi-stage detection**: `RouterAgent.is_multi_intent` (Chinese + English conjunctions).

**Sub-task types**:
`screening`, `interview`, `jd_generation`, `knowledge_query`, `candidate_search`, `report`, `offering`, `onboarding`, `analytics`, `screen_resume`

**Shared context management**:
- `_update_shared_context()`: writes agent outputs to `shared_context` under `{task_type}.{key}` namespace
- `_build_sub_task_input()`: pulls upstream agent outputs as input context
- Uses `output_keys` from each BaseAgent subclass

**Human-in-the-loop**: `_needs_human_review()` returns `True` for `interview`/`offering` types or when agent signals. State is paused via `paused_at_level` + per-sub-task `awaiting_approval`; resume via `/api/v1/human-loop/resume`.

**Persistence**: LangGraph checkpointer (PostgresSaver in prod, MemorySaver in dev) keyed by `thread_id`. Redis index `appr:graph_thread:{approval_id}` (24h TTL) maps approval → thread for resume lookup.

### 4.4 SharedMemory — `app/agents/shared_memory.py` (245 lines)

KV store for cross-agent state:
- Backend: Redis (async) with InMemory fallback
- Namespace isolation: agents use `{type}:{key}:{id}` convention
- Default TTL: 1 hour
- Operations: `get`/`set`/`delete`/`exists`/`keys`/`expire`/`ttl`

---

## 5. Prompts

**Location**: `apps/api/app/agents/prompts/`
**Loader**: `app/agents/prompts/__init__.py` — `load_prompt(agent_name)` function

Each agent gets its system prompt from a file matching its name. BaseAgent auto-loads on first `.system_prompt` access. Prompts are plain text files (Chinese).

---

## 6. Known Issues & Design Decisions

| Issue | Status |
|---|---|
| `screen_resume` missing from `_SUB_TASK_TYPES` | ✅ Already fixed by you (2026-05-29) |
| `knowledge_base` collection name hardcoded in `knowledge.py` | Not configurable — low priority |
| `knowledge_query` in orchestrator task types but no dedicated KnowledgeAgent | Routes through RouterAgent |
| MemoryFact `ObjectValue` field is `dict` not typed/serialized | schema exists in `app/schemas/memory_fact.py` |
| Migration `f4e8d2c1a3b6` creates `memory_facts` table | Already applied |
| Qdrant service requires manual config for 3 separate collection URLs | `qdrant_url` is shared, `collection` names differ |

---

## 7. Test Landscape

| File | Test Count | Focus |
|---|---|---|
| `tests/test_memory_fact.py` | 24 | MemoryFactService CRUD, fact builders, context injection |
| `tests/test_summary_service.py` | 17 | SummaryService generate, retrieve, LLM integration |
| `tests/test_memory.py` | ~ | End-to-end memory pipeline |
| `tests/test_shared_memory.py` | ~ | Redis + InMemory backend KV |
| **Total API test files** | 69 | Full test suite |

---

## 8. Data Flow Summary

```
User Request
    │
    ▼
orchestrator_graph.ainvoke()
    │
    ├─► MemoryFactService.get_structured_context(user_id)   ◄── injects past facts
    │
    ├─► SummaryService.get_relevant(user_id, query)         ◄── retrieves past summaries
    │
    ├─► KnowledgeService.query(question)                    ◄── RAG from knowledge base
    │
    ├─► [Decompose into DAG tasks] → RouterAgent → Specialized Agents
    │       │
    │       ├── ScreeningAgent → candidate search
    │       ├── InterviewAgent → schedule
    │       ├── OfferingAgent → offer (HIL)
    │       ├── ...
    │       │
    │       └── Each → MemoryFactService.record_tool_result()  ◄── writes facts
    │
    ├─► [HIL pause] paused_at_level + awaiting_approval     ◄── checkpointer state
    │
    └─► SummaryService.generate(session_id, messages)       ◄── writes summary
```
