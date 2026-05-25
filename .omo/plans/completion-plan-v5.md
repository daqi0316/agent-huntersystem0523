# V5 整体收官计划 — AI Recruitment System 100%

> 目标: 所有维度推进到 100% — 后端覆盖率 80%+，所有前端页面使用真实 API，基础设施生产就绪，CI/CD 流水线完整验证。

## Current State (Baseline)

| Dimension | Metric | Target | Gap |
|-----------|--------|--------|-----|
| API routes | 60 routes / 22 files | Complete | ✅ Done |
| Backend coverage | 71.58% | 80%+ | **-8.42%** |
| Frontend pages | 14 direct | All integrated | **4 pages mock fallback** |
| Frontend real-API pages | 10 | 14 | **4 pages** |
| E2E specs | 12 files | All green | **Need run** |
| E2E coverage | 12 spec files | Complete | ✅ Structure done |
| CI pipeline | Backend + Frontend + E2E | Full | **Missing Docker build** |
| Coverage threshold | 50% | 70%+ | **-20%** |
| Docker | 4 services + 2 apps | Validated | **Build not in CI** |
| Rate limiting | Not implemented | Enabled | ❌ Missing |
| LLM retry | Not implemented | Backoff | ❌ Missing |
| `.env.example` | 3 files (root + api + web) | Single source | **Consolidate** |
| Python deprecations | 2 warnings | 0 | **-2 warnings** |

## Execution Order

**Phase A → Phase B → Phase C → Phase D → Phase E** (strict dependency order)

---

## Phase A: Coverage Push (71.58% → 80%+)

Priority: by coverage gap (lowest first) × testability (easiest first).

| File | Coverage | Strategy | Target |
|------|----------|----------|--------|
| `knowledge.py` | 20% | Mock Qdrant `get_qdrant()` + LLM `get_llm_client()`; test embed → store → search → QA flow | 80%+ |
| `orchestrator_agent.py` | 21% | Mock `get_llm_client()` + `RouterAgent`; test `decompose()` → `execute_plan()` → `aggregate()` | 80%+ |
| `pipeline.py` | 29% | Mock LLM; test parse → gate → match → final_output flow + fallback | 80%+ |
| `evaluations.py` | 30% | Mock `get_db` with test DB session; test list + get endpoints | 90%+ |
| `aggregator.py` | 35% | Mock LLM; test dimension evaluation flow + error fallback | 80%+ |
| `gen_eval_loop.py` | 34% | Mock LLM; test `GenEvalResult`, generate → evaluate → loop logic | 80%+ |
| `human_loop.py` | 44% | Mock LLM; test pause → resume → feedback → stop flow | 80%+ |
| `omlx_client.py` / `vllm_client.py` | 39% | Mock `httpx.AsyncClient`; test chat, embed, fallback | 80%+ |
| `application.py` | 50% | Extend existing tests, cover error paths | 80%+ |
| `screening.py` | 41% | Mock PipelineAgent + AggregatorAgent; test screen + multi_evaluate | 80%+ |
| `report.py` | 56% | Mock DB queries; test report generation + edge cases | 80%+ |
| `jd_generator.py` | 50% | Mock LLM + DB; test generate + error paths | 80%+ |
| `llm/__init__.py` | 60% | Test `get_llm_client()` with both provider settings | 100% |
| Others | >80% | Small tweaks if needed | 80%+ |

### A.1 — evaluations.py (fastest win, pure DB)

**Files**: `tests/test_evaluations.py`
- Mock `get_db` → inject test applications with candidates
- Test `list_evaluations` with search, status filter, candidate_id filter, pagination
- Test `get_candidate_evaluation` — found / not-found / edge cases
- Test `_build_dimension_scores` + `_clamp` directly as pure functions

**Est**: ~30 min

### A.2 — omlx_client.py / vllm_client.py (HTTP mocking)

**File**: `tests/test_llm_clients.py`
- Mock `httpx.AsyncClient` via `unittest.mock.patch`
- Test `chat()`, `embed()`, `chat_with_fallback()` — success and failure paths
- Test that `omlx_client` vs `vllm_client` are selected correctly via factory

**Est**: ~30 min

### A.3 — knowledge.py (Qdrant + LLM heavy)

**File**: `tests/test_knowledge.py` (existing, needs extension)
- Mock `get_qdrant()` → return fake Qdrant client
- Mock `get_llm_client()` → return fake LLM returning controlled responses
- Test: `ensure_collection`, `add_document`, `search`, `qa_query`
- Test: document not found, empty search, LLM failure fallback
- Use `asyncio.Runner` for event-loop dependent mocks

**Est**: ~45 min

### A.4 — pipeline.py (agent chain)

**File**: `tests/test_pipeline.py` (existing, needs extension)
- Mock `get_llm_client()` on each prompt step (parse → match → gate → final)
- Test: full screening flow with controlled LLM output per step
- Test: individual step failures → graceful fallback
- Test: `PipelineAgent.build_screening_pipeline()` method

**Est**: ~30 min

### A.5 — aggregator.py (multi-dimension eval)

**File**: `tests/test_agents.py` or new `tests/test_aggregator.py`
- Mock `get_llm_client()` → return controlled JSON evaluations
- Test: run with dimensions, without dimensions, LLM failure fallback
- Test: result structure matches expected format

**Est**: ~20 min

### A.6 — gen_eval_loop.py (Gen-Eval iteration)

**File**: new `tests/test_gen_eval_loop.py`
- Test `GenEvalResult` data class: `to_dict()`, construction
- Mock LLM for generate step + evaluate step
- Test: iterate until passing, max iterations reached, LLM failure recovery
- Test JD generation flow end-to-end

**Est**: ~30 min

### A.7 — orchestrator_agent.py (task decomposition)

**File**: `tests/test_orchestrator.py` (existing, needs extension)
- Mock `get_llm_client()` + `RouterAgent`
- Test: `guess_type()` keyword matching (all types)
- Test: `decompose()` with LLM → fallback to keyword
- Test: `execute_plan()` with sub-agents, aggregator fallback
- Test: `register()` + sub-agent dispatch

**Est**: ~30 min

### A.8 — human_loop.py (pause/resume/feedback)

**File**: `tests/test_human_loop.py` (existing, needs extension)
- Mock LLM; test `pause()`, `resume()`, `request_feedback()`, `emergency_stop()`
- Fix `datetime.utcnow()` deprecation → `datetime.now(datetime.UTC)`
- Test timeout + auto-resume behavior

**Est**: ~20 min

### A.9 — application.py / screening.py / report.py / jd_generator.py

**File**: Extend existing test files
- application.py: test error paths (DB failure, not found)
- screening.py: mock PipelineAgent + AggregatorAgent, test screen + multi_evaluate + get_pipeline_progress
- report.py: test with mock DB data, edge cases (no data, empty results)
- jd_generator.py: mock LLM + DB, test generation + error paths

**Est**: ~40 min

### A.10 — Final coverage verification

```bash
cd apps/api && python -m pytest tests/ --cov=app --cov-report=term-missing
```
Target: 80%+ overall, no file below 70%.

**Est**: ~10 min

---

## Phase B: Frontend Integration Completion

### Current Status
| Page | Real API | Mock Fallback |
|------|----------|---------------|
| dashboard | ✅ Yes | Yes (left in) |
| jd-generator | ✅ Yes | No |
| screening | ✅ Yes | No |
| candidates | ✅ Yes | No |
| jobs | ✅ Yes | No |
| auth/login | ✅ Yes | No |
| evaluation | 🔄 Partial | Yes |
| interview | 🔄 Partial | Yes |
| talent-profile | 🔄 Partial | Yes |
| knowledge | ❌ TBD | Likely |
| reports | ✅ Yes | TBD |
| settings | ❌ TBD | Likely |
| (auth) (register) | ✅ Yes | No |
| (dashboard) | ✅ Yes | No |

### B.1 — evaluation/page.tsx → real `/evaluations` API
- Current: `/api/v1/evaluations` already connected ✅, strip mock fallback completely

**Est**: ~10 min

### B.2 — interview/page.tsx → real `/interviews` API
- Current: `/api/v1/interviews` exists with 6 CRUD endpoints
- Connect interview list, create form, detail view
- Remove mock data paths

**Est**: ~20 min

### B.3 — talent-profile/page.tsx → real evaluations + interviews
- Current: fetches `/evaluations/{candidate_id}`
- Add interview history, application history from real endpoints
- Remove mock fallback

**Est**: ~20 min

### B.4 — knowledge/page.tsx, settings page
- Check if these pages need APIs or are static UI only
- If API-backed, connect to existing endpoints

**Est**: ~10 min

---

## Phase C: Infrastructure Hardening

### C.1 — Rate limiting middleware

**File**: `apps/api/app/core/rate_limit.py`
- FastAPI middleware using Redis-backed counters
- `@RateLimiter(limit=100, window=60)` decorator
- Configurable per-endpoint limits
- Return 429 with `Retry-After` header when exceeded
- Apply to public endpoints (auth, search, evaluation)

**Est**: ~30 min

### C.2 — LLM retry with exponential backoff

**File**: `apps/api/app/llm/retry.py`
- Wrap `chat()` and `embed()` in retry decorator
- Backoff: 1s → 2s → 4s → 8s → 16s (max 5 retries)
- Respect `Retry-After` header if LLM returns 429
- Log each retry attempt with duration
- Max total wait: ~31s

**Est**: ~20 min

### C.3 — Consolidate `.env.example` files

Currently 3 files:
- `/.env.example` (root — 42 lines, has both API + web vars)
- `apps/api/.env.example` (48 lines, API-specific)
- `apps/web/.env.example` (7 lines, web-specific)

**Action**: Keep `apps/api/.env.example` as API source of truth; keep `apps/web/.env.example` as web source of truth; remove redundant root `.env.example`. Update root `README.md` quickstart to reference per-app files.

**Est**: ~10 min

### C.4 — Fix Docker Python version mismatch

Current: Docker uses `python:3.13-slim-bookworm`, CI uses `3.14`
**Action**: Bump Dockerfiles to `python:3.14-slim-bookworm`

**Est**: ~5 min

### C.5 — Fix Python deprecation warnings

**File**: `apps/api/app/agents/human_loop.py` lines 149, 157
- `datetime.utcnow()` → `datetime.now(datetime.UTC)`

Check for other occurrences:
```bash
grep -rn "utcnow" apps/api/app/
```

**Est**: ~10 min

### C.6 — Add health check on all Docker services

Current: API has healthcheck, web doesn't. Add healthcheck for web service, verify postgres/redis/qdrant healthchecks work.

**Est**: ~10 min

---

## Phase D: E2E Verification

### D.1 — Run full E2E suite locally

```bash
# Start API + web
cd apps/api && uvicorn app.main:app --port 8000 &
cd apps/web && pnpm dev &

# Run all specs
cd apps/web && npx playwright test
```

Fix any failures per spec:
- auth.spec.ts — register + logout flow
- dashboard.spec.ts — stats rendering
- candidates.spec.ts — list + CRUD
- jobs.spec.ts — list + CRUD
- screening.spec.ts — pipeline trigger
- evaluation.spec.ts — evaluation list
- interview.spec.ts — CRUD
- reports.spec.ts — report generation
- talent-profile.spec.ts — candidate detail
- knowledge.spec.ts — document search
- jd-generator.spec.ts — JD generation
- settings.spec.ts — profile settings

**Est**: ~30 min

### D.2 — Verify Playwright CI configuration

- Confirm chromium binary is installed
- Confirm API healthcheck loop works
- Confirm artifacts upload works

**Est**: ~10 min

---

## Phase E: CI/CD Enhancement

### E.1 — Add Docker build validation to CI

**File**: `.github/workflows/ci.yml`

Add a `docker` job:
```yaml
docker:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Build API Docker image
      run: docker build -t ai-recruitment-api apps/api/
    - name: Build Web Docker image
      run: docker build -t ai-recruitment-web -f apps/web/Dockerfile .
```

**Est**: ~15 min

### E.2 — Bump coverage threshold

**File**: `apps/api/pyproject.toml`
```toml
[tool.coverage.report]
fail_under = 70
```

Only after Phase A completes and 70%+ is verified.

**Est**: ~5 min

### E.3 — Add `pnpm audit` / dependency check

**File**: `.github/workflows/ci.yml`
- Add `pnpm audit --audit-level=high` after install step
- Add `pip audit` or safety check for Python deps

**Est**: ~10 min

### E.4 — Add `pnpm test` to frontend CI job

**File**: `.github/workflows/ci.yml`
- Run frontend unit tests in the `frontend` job
- Currently only lint + build

**Est**: ~10 min

---

## Time Estimates

| Phase | Tasks | Est. Time |
|-------|-------|-----------|
| **Phase A** Coverage | 10 sub-phases (A.1–A.10) | ~4.5h |
| **Phase B** Frontend | 4 page integrations | ~1h |
| **Phase C** Infra | 6 items (C.1–C.6) | ~1.5h |
| **Phase D** E2E | 2 items (D.1–D.2) | ~40min |
| **Phase E** CI/CD | 4 items (E.1–E.4) | ~40min |
| **Total** | 26 items | **~8h** |

---

## Verification Gates

### Gate A — Coverage
```bash
cd apps/api && python -m pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80 2>&1 | tail -20
```
✅ ≥80% overall, no file below 70%

### Gate B — Frontend
Visit each page, confirm renders with real data, no console errors.
✅ All 14 pages load without mock data

### Gate C — Infra
- Start API, hit rate-limited endpoint 101 times → 429 on 101st
- Trigger LLM error → verify retry with backoff in logs
✅ Rate limiting working, LLM retry working, no deprecation warnings

### Gate D — E2E
```bash
cd apps/web && npx playwright test --reporter=list
```
✅ All 12 spec files green

### Gate E — CI/CD
Docker build passes, pnpm audit passes, coverage threshold met.
✅ Full pipeline green

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Qdrant/LLM hard to mock in tests | High | High | Use `@pytest.fixture` with `AsyncMock` for all external deps; accept 70-80% on heavy-LLM files if mocking is impractical |
| E2E flakiness | Medium | Medium | Add `retries: 2` in `playwright.config.ts`; increase timeouts for slow pages |
| Docker build regression | Low | Medium | Validate Docker builds locally before CI change |
| Frontend page refactor conflicts | Low | Medium | Work one page at a time, verify each independently |
