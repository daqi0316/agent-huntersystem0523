# Anchored Summary

## Goal
Complete the full auth system (Phase 2), JD Generator API + Knowledge RAG (Phase 3), E2E/agent tests (Phase 4), and CI/CD pipeline — all backed by Docker PostgreSQL.

## Constraints & Preferences
- FastAPI backend + Next.js 14 frontend, monorepo with Turborepo + pnpm
- Backend: async SQLAlchemy + Pydantic v2 schemas + service layer
- Frontend: `'use client'`, shadcn/ui components
- Build must pass `pnpm build`
- `turbo.json` uses `tasks` field (Turborepo 2.x), not `pipeline`

## Progress
### Done
- **Phase 2 — Auth System complete**: Backend JWT auth routes (register/login/me), frontend login page + AuthGuard + Header auth state, Docker infra (postgres/redis/qdrant), Alembic migration (5 tables seeded with admin+hr users)
- **Infra fixes**: Alembic `env.py` imports models; pinned `bcrypt==4.0.1`; `router.py` registers all 7 agent routers + CRUD routers
- **Phase 3 — All 7 Agent patterns wired**: `agent.py`, `retrieval.py`, `pipeline.py`, `router_route.py`, `parallel.py`, `orchestrator.py`, `loop.py`, `human_loop.py`, `tools.py`, `knowledge.py`, `memory.py` — all register in OpenAPI spec and pass import verification
- **Phase 4 — Test suite complete (46 tests)**:
  - `test_agent.py` (20 tests): auth protection (parameterized across 5 endpoints), chat success/system-prompt/validation, JD generation success/validation, knowledge query success/validation, retrieval search/embed success and validation
  - `test_auth.py` (9 tests): register success/duplicate/invalid-email, login success/wrong-password/nonexistent, /me valid/no-token/invalid-token
  - `test_candidates.py` (6 tests): list, create, get, get-404, update, delete
  - `test_jobs.py` (6 tests): list, create, get, get-404, update, delete
  - `test_agents.py` (3 tests): single-agent, router-agent, aggregator-agent unit tests
  - `test_pipeline.py` (2 tests): stub screening + pipeline gate
- **Test infra fixes**: 
  - `pytest.ini` with `asyncio_mode = auto`
  - `conftest.py` with session-scoped `event_loop` + `engine.dispose()` cleanup per test
  - `RegisterRequest.email` → `EmailStr` (invalid emails return 422)
  - UUID validation in `JobService.get_by_id` / `CandidateService.get_by_id` (non-UUID → 404)
  - All tests use valid DB enum values (`active`/`archived`/`draft`/`closed`) and unique emails
  - Agent tests mock LLM/KnowledgeService/JDGeneratorService for deterministic execution
- **CI/CD**: `.github/workflows/ci.yml` — Docker services (postgres/redis/qdrant) + backend (import check, migration, pytest with coverage) + frontend (lint, pnpm build)
- `pnpm build` passes with zero errors

### In Progress
- (none)

### Blocked
- Agent endpoints require a running LLM (vLLM/omlx) for un-mocked runtime — `test_agent.py` uses mocks for deterministic CI

## Key Decisions
- Tests run against real Docker PostgreSQL (no test DB or SQLite isolation) — simpler for internal validation, avoids separate test cluster
- `engine.dispose()` called after each test to prevent stale asyncpg connections
- Agent E2E tests use `unittest.mock.patch` to mock `get_llm_client`, `JDGeneratorService`, and `KnowledgeService` — tests are deterministic and CI-friendly
- CI uses `pytest --cov-fail-under=50` to keep the floor reasonable without blocking on uncovered agent modules

## Next Steps
1. Start vLLM container (`docker compose --profile gpu up vllm -d`) for un-mocked agent endpoint verification
2. Add frontend component tests (Vitest or Playwright)
3. Write comprehensive AI-powered agent E2E tests (e.g., actual JD generation flow once LLM is running)
4. Deploy staging environment (Vercel for frontend, Railway/Fly.io for backend)

## Critical Context
- Docker services running: postgres:5432 (healthy), redis:6379 (healthy), qdrant:6333-6334 (healthy)
- Admin credentials (seed): `admin@example.com` / `admin123`; HR user: `hr@example.com` / `hr123456`
- LLM settings: provider=omlx, base_url=http://localhost:8001/v1, model=qwen3.6 — no vLLM container by default
- **46 tests total** across 6 test files; all pass
- `pytest-asyncio==1.3.0` (latest for Python 3.14); session-scoped `event_loop` fixture required
- Database enums: `candidate_status` = (ACTIVE, ARCHIVED, BLACKLISTED); `job_status` = (DRAFT, ACTIVE, PAUSED, CLOSED)
- API accepts `status` as plain string (not enum) and converts via SQLAlchemy mapped column
- CI workflow: backend job uses GitHub Actions service containers for postgres/redis/qdrant; frontend job caches pnpm store

## Relevant Files
- `tests/test_agent.py` — 20 agent/retrieval E2E tests with mocks
- `tests/test_auth.py` — 9 auth E2E tests
- `tests/test_candidates.py` — 6 candidate CRUD tests
- `tests/test_jobs.py` — 6 job CRUD tests
- `tests/test_agents.py` — 3 unit tests for agent patterns
- `tests/test_pipeline.py` — 2 pipeline stub tests
- `tests/conftest.py` — FastAPI test client fixture (real PostgreSQL, engine disposed per test)
- `.github/workflows/ci.yml` — CI/CD pipeline

## 1. User Requests (As-Is)
- "Continue if you have next steps" → continued with all remaining P4 work

## 2. Final Goal
Auth system (Phase 2), all 7 Agent patterns (Phase 3), full E2E test suite (46 tests, Phase 4), and CI/CD pipeline (Phase 4) — all green.

## 3. Work Completed (This Session)
- **Phase 4 test_agent.py**: 20 tests covering all 5 agent/retrieval endpoints — auth protection (10 parameterized tests), handler logic with mocked LLM/services (10 tests)
- **Phase 4 CI/CD**: `.github/workflows/ci.yml` — Docker service containers for postgres/redis/qdrant, backend import check + migration + pytest with coverage, frontend lint + pnpm build
- **All 46 tests passing** (26 existing + 20 new)
- Anchor summary updated

## 4. Remaining Tasks
- Start vLLM container for un-mocked agent endpoint testing
- Frontend component tests (Vitest/Playwright)
- Production deployment (Vercel + Railway/Fly.io)

## 5. Active Working Context (For Seamless Continuation)
- **Files**: `tests/test_agent.py`, `.github/workflows/ci.yml`
- **Code in Progress**: 46/46 tests passing; CI/CD workflow written
- **State**: Docker services up; seed data present; all CRUD + agent E2E tests passing with mocks

## 6. Explicit Constraints (Verbatim Only)
- "搭建一套可售卖的 AI 招聘 SaaS 系统，包含 7 种 AI Agent 架构模式、11 个前端页面、企业级后端基础设施"
- "基于 `AI_Recruitment_System_PRD.md` v1.0"
- "Monorepo: Turborepo + pnpm"
- "前端: Next.js + TypeScript + Tailwind + shadcn/ui"
- "后端: FastAPI + Uvicorn + Gunicorn"
- "数据库: PostgreSQL 16 (主从 + 读写分离)"
- "向量库: Qdrant + bge-m3 嵌入"
- "缓存: Redis 7"
- "消息队列: RabbitMQ"
- "AI推理: vLLM + Qwen3.6 (本地) / omlx (开发)"
- "状态管理: Zustand (客户端) + React Query (服务端)"
- "先做好规划,然后搭建项目架构"

## 7. Agent Verification State (Critical for Reviewers)
- **Current Agent**: Sisyphus (Primary)
- **Verification Progress**: All 46 pytest tests passing (26 existing + 20 new agent E2E); CI/CD workflow written; Docker infra running; Alembic migration applied; pnpm build passes
- **Acceptance Status**: Phase 2-4 complete; ready for deployment

## 8. Delegated Agent Sessions
- (none — all work done directly by Sisyphus)
