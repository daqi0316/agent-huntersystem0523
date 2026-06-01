# Phase U Findings: Operations + Observability + Production Ready

**Date**: 2026-06-01
**Phase**: U (Operations + Observability + Production Ready)
**Branch**: main
**Status**: U.1–U.9 complete; U.10 deferred

---

## 1. Discovery: U.1–U.6 + U.8 Already Implemented

Investigation on 2026-06-01 found that the backend half of Phase U was **fully implemented** during Phase R's atomic commits (commit `7c5d7ea` feat(models+services+tools+skills) + `692a96b` feat(agents) + `e9b9e81` feat(web)).

Frontend gaps: U.7 (AuditPanel) and U.9 (approval countdown UI) did not exist — both were authored in this phase.

---

## 2. U.1–U.10 Verification Matrix

| # | Task | File | Status | Evidence |
|---|---|---|---|---|
| U.1 | OperationLog `error_category` / `immutable` / `superseded_by` | `app/models/operation_log.py` | ✅ DONE | Lines 42-53: 3 fields + comment block; `idx_oplog_error_cat` index |
| U.2 | ApprovalService take over HumanLoop persistence | `app/services/approval_service.py` | ✅ DONE | 165 lines, `create/resolve/expire_pending/list_pending/list_history` with event_bus publishing |
| U.3 | Refactor `human_loop.py` to use ApprovalService | `app/agents/human_loop.py` | ✅ DONE | Line 17: `from app.services.approval_service import ApprovalService`; line 52: `_with_db` helper |
| U.4 | `operation_stats_hourly` + 5-min UPSERT | `app/services/aggregation_service.py` | ✅ DONE | `run_aggregation()` + `aggregation_loop()` (5-min interval) |
| U.5 | `GET /api/v1/audit/logs` + filtering | `app/api/audit.py` | ✅ DONE | `/logs` (lines 21-68) with `agent_name`/`error_category`/`from_date`/`to_date` filters; `/stats` (lines 71-100) |
| U.6 | `auto_expire()` + SSE | `app/services/operation_service.py` | ✅ DONE | `expire_pending()` in approval_service.py:100-116; `sse_generator()` in operation_service.py:210-230 |
| U.7 | AuditPanel 前端组件 | `apps/web/components/features/audit/audit-panel.tsx` | ✅ NEW | 250 lines, filters (agent_name/error_category), expand rows, status badges, type-checked clean |
| U.8 | AI 健康监测面板 | `apps/web/components/features/monitoring/ai-health.tsx` | ✅ DONE | 155 lines, success rate ring + Agent P95 trend |
| U.9 | Dashboard 集成 + 审批倒计时 UI | `apps/web/components/features/approvals/approval-countdown.tsx` + dashboard/page.tsx | ✅ NEW | 220 lines, 60s auto-refresh, urgent threshold (< 6h), 30s tick for live countdowns; integrated into dashboard row 3 |
| U.10 | E2E 回归 + 覆盖率守门 ≥ 90% | (Playwright) | ⏸ DEFERRED | Requires dev server (OMLX/vLLM/API) not available in CLI |

---

## 3. New Files Created in Phase U (this commit)

| File | Lines | Purpose |
|---|---|---|
| `apps/web/components/features/audit/audit-panel.tsx` | 250 | AuditPanel widget — list + filter + expand |
| `apps/web/components/features/approvals/approval-countdown.tsx` | 220 | Pending approvals with live countdown + approve/reject actions |
| `apps/web/app/(dashboard)/audit/page.tsx` | 142 | /audit route with stats banner + AuditPanel |
| `apps/web/app/(dashboard)/dashboard/page.tsx` | +1 col (modified) | Added ApprovalCountdown to row 3 alongside OperationFeed |

**TypeScript validation**: `npx tsc --noEmit` filtered to the 4 files returned **0 errors**.

---

## 4. Architecture Verification

### Backend — Event-driven approval flow
```
create_proposal → ApprovalService.create() → event_bus.publish("approval.created")
                                              ↓
                                       sse_generator() pushes
                                              ↓
                                       Frontend EventSource
```

### Backend — Auto-expire pattern
```python
async def expire_pending(self) -> int:
    """Scan pending approvals where expires_at < now → mark EXPIRED → publish SSE."""
```

Called from `list_pending()` (line 119) and `aggregation_loop` (line 130 — 5-min tick).

### Frontend — ApprovalCountdown lifecycle
1. **Initial load** (mount): `api.get("/human_loop/pending")`
2. **Periodic refresh**: every 60s
3. **Tick**: every 30s (re-render for countdown labels without re-fetching)
4. **Urgent threshold**: < 6h remaining → red border + badge
5. **Optimistic UI**: on approve/reject, remove from local state; backend persists via `/human_loop/approve`

### Frontend — AuditPanel features
- Filters: agent_name (10 options) + error_category (3 options) — server-side
- Expand row to see input/output/error_message
- Error category color coding (system=red, user=amber, business=slate)
- Status badges (pending/running/completed/failed/cancelled/awaiting_approval)
- Duration formatter (ms < 1000 → "Xms", else "X.XXs")
- Empty state, loading skeleton, error alert

---

## 5. U.10 E2E — Why Deferred

The plan's U.10 deliverable is "E2E 回归 + 覆盖率守门 ≥ 90%" (E2E regression + coverage gate ≥ 90%).

Per current state (post-S.8):
- **1382 tests collected**
- **1339 passed** (96.9% pass rate)
- **37 failed** — all pre-existing legacy issues (test_human_loop_api + test_agent_service)
- **2 xfailed** — legacy OrchestratorAgent awaiting_approval flow
- **4 skipped** — pre-existing

**Current coverage**: 92% per `anchor-summary.md` (Phase R deliverable).

**Mitigation for U.10**:
- Playwright E2E requires a real deployment (OMLX:8000, vLLM:8001, API:8888, frontend:3000)
- All four are external services not available in this CLI
- The 37 pre-existing failures are out of U scope (test modernization pass needed first)
- Coverage gate (≥ 90%) is already met

**Recommended next step**: spin up dev stack via `make dev` or `docker-compose up`, then run `npx playwright test` to exercise the new /audit page + approval-countdown dashboard widget.

---

## 6. Decisions Surfaced by Phase U

### A. Phase U is mostly a verification phase + 2 frontend files
Backend half (U.1–U.6) was implemented in Phase R. U.7 + U.9 frontend are the only net-new code. U.8 was already authored.

### B. Single approval endpoint surface
There's no dedicated `app/api/approvals.py`. Approvals live in `app/api/human_loop.py` with routes /events, /schedule, /approve, /pending, /history, /resume, /stop. This is intentional — HumanLoop and approval are a single domain (the "pause-for-human" pattern).

### C. SSE channel unification
`event_bus.publish()` events flow through `sse_generator()` to all connected `EventSource` clients. The frontend `operation-feed.tsx` already subscribes; new components can subscribe the same way.

### D. ApprovalCountdown uses 30s tick + 60s refresh
30s tick for countdown labels (cheap, no network). 60s refresh for new approvals (heavier, network-bound). This balances perceived responsiveness against backend load.

### E. /audit page uses AuditStatsBanner + AuditPanel
Stats banner (3 cards: total ops / system errors / category distribution) sits above the full-width audit log panel. Single page, single scroll, no tab navigation.

---

## 7. U Phase → Sunset Handoff

**R + S + T + U = 19 atomic commits** (9c80b30 → 5519653 → [this]).

**Deferred items**:
- **S.6 sunset 2026-06-08**: Hard-delete `OrchestratorAgent` + `OrchestratorSession` after 4 migration PRs
  - `human_loop /resume` → LangGraph checkpointer (PostgresSaver)
  - `agent_service` step 1 → `create_orchestrator_graph().ainvoke()`
  - Test modernization for 37 pre-existing failures
  - `__init__.py` re-exports cleanup
- **T.8 E2E**: Upload → parse → evaluate Playwright spec (needs dev stack)
- **U.10 E2E + coverage gate**: Playwright suite + CI integration (needs dev stack)

**Production-readiness assessment**:
- ✅ OperationLog immutable + correction chain (`superseded_by`)
- ✅ HumanLoop persistence survives restart (DB-backed Approval)
- ✅ Auto-expiry of stale approvals
- ✅ Real-time SSE for operation + approval events
- ✅ AI health monitoring (success rate + P95)
- ✅ Audit log query with filters
- ⏸ Production PostgresSaver for LangGraph (MemorySaver currently in `_get_graph()`)
- ⏸ Real deployment smoke test (Playwright against dev stack)

---

## 8. Summary

| Metric | Value |
|---|---|
| Commits this phase | 1 (this commit) |
| New files | 3 (audit-panel.tsx, approval-countdown.tsx, audit/page.tsx) |
| Modified files | 1 (dashboard/page.tsx) |
| TypeScript errors | 0 |
| New tests | 0 (U.10 deferred) |
| Backend lines verified | 405 (approval_service + aggregation_service + audit + operation_log) |
| Frontend lines added | ~613 (audit-panel 250 + approval-countdown 220 + audit page 142 + dashboard 1) |

Phase U is **functionally complete** for U.1–U.9. U.10 (Playwright E2E + coverage gate) requires a live dev deployment and is deferred to the next deployment cycle.
