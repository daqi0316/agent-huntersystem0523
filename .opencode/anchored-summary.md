# Overall Progress: ~90%

## What We've Built
AI Recruitment System — full-stack hiring platform with agent orchestration, multi-dimensional evaluation, interview scheduling, and RAG-powered knowledge base.

**AgentOps Platform (new since 2026-06-10, P1+P2)**: AgentOps 可观测平台地基完成——15 个模块、Langfuse exporter、异步队列、熔断器、脱敏治理、事件协议。P2-A 招聘业务事件深化（6 类事件 + emitter + store），P2-B Agent Graph 深度观测（orchestrator/LLM/tool span 标准化）。

| Layer | Stack | Status |
|-------|-------|--------|
| Backend API | FastAPI + SQLAlchemy + Alembic | ✅ Core complete |
| Agent System | Pipeline / Orchestrator / Router / GenEval / HumanLoop | ✅ Phase 1 done |
| Frontend | Next.js 14 + tRPC + Recharts + Tailwind | ✅ 15 routes |
| Testing | Pytest (15 agentops test files + backend regression) | ✅ All pass |
| LLM | OMLX (Qwen3.6) / vLLM | ✅ Connected |
| **AgentOps Platform** | `app/agentops/` — schemas, context, providers, queue, circuit breaker, sanitizer, exporter, events, tracing | ✅ **P1+P2 complete** |

---

## Recently Completed

### Session 2026-06-10 — AgentOps Platform P1+P2

#### P0/P1 Core Platform (Sprint A-D)
| Module | Files | Tests |
|--------|-------|-------|
| Event Schema v1 | `agentops/core/schemas.py` (6 event types + schema_version) | `test_agentops_schemas.py` |
| Context Propagation | `agentops/core/context.py` (AgentOpsContext + contextvars) | `test_agentops_context.py` |
| NoopProvider | `agentops/providers/noop.py` (zero side-effect) | `test_agentops_noop_provider.py` |
| CompositeProvider | `agentops/providers/composite.py` (multi-provider) | `test_agentops_composite_provider.py` |
| Privacy Sanitizer | `agentops/privacy/sanitizer.py` (reuse pii_filter) | `test_agentops_sanitizer.py` |
| Async Queue | `agentops/reliability/queue.py` (drop_new/drop_oldest) | `test_agentops_queue.py` |
| Circuit Breaker | `agentops/reliability/circuit_breaker.py` (5 fail → 60s per-provider) | `test_agentops_circuit_breaker.py` |
| LangfuseExporter | `agentops/exporters/langfuse_exporter.py` (optional dep, warning-only) | `test_agentops_langfuse_exporter.py` |
| Runtime | `agentops/runtime.py` (singleton + shutdown) | `test_agentops_runtime.py` |
| Config | `core/config.py` (AgentOps/Langfuse settings, default disabled) | — |

#### P2-A: Recruitment Business Events
- `agentops/events/` — 6 business event schemas (resume.parse, screening, jd.generate, interview.schedule, offer, onboarding)
- `agentops/events/emitter.py` — `emit_recruitment_event()` unified entry
- `agentops/events/store.py` — local event cache for offline consumption
- `models/operation_log.py` — extended with event_type, business_entity_id, business_entity_type, business_payload
- Alembic migration `p2_a_business_events.py`

#### P2-B: Agent Graph Deep Observation
- `agentops/tracing.py` — `trace_operation()` / `span_operation()` for OperationLog ↔ trace_id linkage
- `operation_service.py` — read/query with trace_id filter
- `GET /api/v1/operations` — route with trace_id/task_type/status filter
- `orchestrator_graph.py` — orchestrator_span wrapping decompose/build_dag/execute_level
- `agent_service.py` — `chat_with_tools` root trace creation
- LLM Generation standardization (tool_planning, final_response, summary naming)
- Tool Invocation standardization (screening/interview/jd/resume_parser/evaluation spans)

---

## Pending Work

### Sprint E: Pre-validation Before P1 (current)
| Item | Description |
|------|-------------|
| **E.1** | Run all `test_agentops_*.py` — verify pass |
| **E.2** | Run `test_pii_filter.py` + `test_llm_clients.py` regression |
| **E.3** | Run ruff on `app/agentops` + new tests |
| **E.4** | Confirm `app.main` importable |
| **E.5** | Summary verdict → decide P1 `route_single()` root trace |

### P1 (next): Core Pipeline Full Observability
- `route_single()` root trace (Stage 2, §19.5)
- LLM Generation standardized wrapper (Stage 6, §19.6)
- Tool Invocation standardized entry (Stage 7, §19.7)
- OperationLog ↔ trace_id binding
- session_id propagation

### P2/3 (later): Quality Evaluation System
- Score taxonomy & score schema (Stage 4, §19.10)
- Rule evaluators + LLM judge evaluators
- Human feedback API (Stage 11, §19.11)
- Dataset / Experiment pipeline (Stage 5, §19.12)
- Dashboard / Governance (Stage 6, §19.13-14)

---

## Infrastructure

| Service | Port | Status |
|---------|------|--------|
| PostgreSQL | 5432 | ✅ docker |
| Redis | 6379 | ✅ docker |
| Qdrant | 6333 | ✅ docker |
| MinIO | 9000 | ✅ docker |
| OMLX Qwen3.6 | 8000 | ✅ auto |
| API Server | 8888 | ❌ stopped |
| Frontend | 3000 | ❌ stopped |

---

## Key Config
- LLM: `Qwen3.6-35B-A3B-4bit` via OMLX at `http://localhost:8000/v1`
- API port: 8888 (avoid OMLX conflict on 8000)
- Test user: `e2e-tester@test.com` / `E2ePass123!`
- `pyproject.toml`: no editable build, use `uv pip install` + `uv run --no-sync`
