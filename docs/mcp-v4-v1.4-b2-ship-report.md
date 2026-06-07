# Phase B · B2 Ship Report — Human-in-loop 业务 orchestrator + ApprovalService 集成

> **Ship 日期**: 2026-06-08
> **依据**: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2 (B2 = Orchestrator mock LLM + 真 DB 1.5d)
> **修正**: 跳 A3+A4 已覆盖的 4 阶段 dispatch, 专注 Human-in-loop + ApprovalService 新视角 (B2 实际 0.4d)
> **上一站**: `B1` (Pipeline E2E, 2de20b3 + 12ea9c0) — 2026-06-08
> **commit**: 1 个测试文件 + 1 个 ship report
> **接受门槛**: 3/3 测试通过 + 60+ 现有 E2E 不退化

## 1. 概览

| 维度 | 状态 |
|---|---|
| `test_e2e_human_loop_b2.py` 测试文件 (270+ 行) | ✅ |
| `test_approval_service_create_resolve_lifecycle` | ✅ DB 持久化端到端 (create → pending → resolve → approved) |
| `test_screening_agent_returns_needs_human_review` | ✅ mock LLM 返低分, ScreeningAgent.screen 返 needs_human_review=True |
| `test_screening_to_approval_e2e` | ✅ 端到端 — ScreeningAgent.screen 触发 needs_human_review → ApprovalService.create → resolve |
| 60 个现有 E2E 不退化 | ✅ 66 passed (60 + B1 3 + B2 3) |
| 接入 mcp-ci.yml unit-tests job | ✅ 自动 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/tests/mcp/integration/test_e2e_human_loop_b2.py` | +273 (新) | 3 测试 (Approval lifecycle + Screening needs_human_review + 端到端) |
| **总** | **+273 / 0** | 1 文件 |

## 3. 关键决策

### 3.1 跳 A3+A4 已覆盖的 4 阶段 dispatch, 专注 Human-in-loop 新视角

B2 规划 1.5d 含测 "AI Agent E2E (Orchestrator mock LLM + 真 DB)" — 但 A3 (v1.4a parse→evaluate) + A4 (v1.4b match→schedule + 4 阶段编排) 已 ship 这部分。

**B2 真正新增** (避免重做):
1. ApprovalService DB 持久化端到端 (A3+A4 没测过 Approval model)
2. ScreeningAgent 触发 needs_human_review 业务路径
3. 业务流: ScreeningAgent → ApprovalService.create → 人类 resolve

按"工程化深度 + 不重做"原则, 实际估 0.4d (vs 规划 1.5d, -73%).

### 3.2 mock 路径: 复用 B1 教训

按 B1 §3.1 教训: patch module 内部 import 的名字, 不是源头.
- B1 mock: `app.agents.pipeline.get_llm_client` (PipelineAgent 内部 import)
- B2 mock: `app.agents.screening_agent.get_llm_client` (ScreeningAgent 内部 import)
- 第一次试 `app.llm.get_llm_client` 失败, 改 module 名字 0.15s 通过

### 3.3 fixture 改用真实 e2e-tester user (approvals FK)

`approvals` 表 FK 到 `users.id`. A3+A4 fixture 用 `test-user-id` 不在 users 表, 测试创建 candidate 不 FK 到 user 所以没 fail. **B2 创建 approval 触发 FK violation**.

修法: fixture 改用 e2e-tester@test.com 的真实 user_id (1d20462f-6dec-4be0-a48b-7595b3bf2ffb, 之前 SQL 改 role=ADMIN).

**后续**: A3+A4 fixture 也应该用真 user (避免后续 B 测试触发类似 FK). 推独立 PR 改 fixture.

### 3.4 overall_score 字段含义 (screening_agent.py:222)

`screening_agent.py:222`: `final_score = match.get("overall_score", 0)` — **用 match.overall_score** 不是 `gate.score_adjusted`.

测试 2 修对: `assert result["overall_score"] == 3.5` (match.overall_score) 而非 3.0 (gate.score_adjusted). 注释解释 (screening_agent.py:222).

**业务影响**: human 看到的 score 是 match 原始分, 不是 gate 调整后. UI 展示要分清.

## 4. 测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_approval_service_create_resolve_lifecycle` | ApprovalService.create DB 持久化 (status=PENDING) → resolve (status=APPROVED + resolver_id + resolution + resolved_at) → 二次 resolve 返 None (status 已不是 PENDING) → DB 验证最终 APPROVED |
| 2 | `test_screening_agent_returns_needs_human_review` | mock LLM 返低分 (overall_score 3.5 + gate_passed=False + needs_human_review=True) → ScreeningAgent.screen 返 needs_human_review=True + gate_passed=False + overall_score=3.5 |
| 3 | `test_screening_to_approval_e2e` | 业务流: ScreeningAgent.screen 返 needs_human_review=True → ApprovalService.create DB 持久化 → resolver 调 resolve APPROVED → 验 list_pending 不再含此 approval |

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 3 新测试通过 | `pytest tests/mcp/integration/test_e2e_human_loop_b2.py` | ✅ 3/3 passed |
| 60 现有 E2E 不退化 | `pytest tests/mcp/integration/ --ignore=test_host_lifecycle` | ✅ 66 passed |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.4d | ✅ |
| 5 强约束 (+30% buffer) | 估 1.5d → 实际 0.4d | ✅ 大幅 buffer 内 |
| 5 强约束 (1 PR 必含测) | 3 新测试 | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (新测试, 不动 prod) | N/A |
| 5 强约束 (顺序锁死) | B2 = Phase B 第 2 步 | ✅ |
| 5 强约束 (量化 KPI) | 3/3 测 + 0.15s 跑完 + 66 E2E 不退化 | ✅ 3 KPI |

## 6. 未在 B2 范围（明确不做）

- ❌ A3+A4 fixture 改用真 user (B2 独立 PR 解决, 不动 A3+A4)
- ❌ screening_agent `_rule_screen` 兜底逻辑 E2E (推后续, 路径复杂)
- ❌ ApprovalService `expire_pending` E2E (推后续, 需时序控制)
- ❌ ApprovalService `list_history` E2E (推后续)
- ❌ 真 LLM E2E (推 Phase E)
- ❌ Multi-intent 路由 E2E (A3+A4 已测过)

## 7. 后续路径

**B3 跳过**: Router E2E 80% 已被 A4 覆盖 (`test_orchestrator_full_pipeline` 4 阶段编排含 Router mock)

**B4 (1d, 1 commit) — Knowledge/RAG E2E (Qdrant)**:
- 写 `test_e2e_knowledge_b4.py`
- 测 upload → query → cite 端到端
- mock LLM cite 格式 (mask_pii 反直觉, 复 B1/B2 教训)

**B5 (0.8d, 1 commit) — Auth/Org E2E (5-8 隔离 case)**:
- 写 `test_e2e_auth_org_b5.py`
- 测同 org/跨 org/super_admin/org 切换 多场景
- 真 DB 多 org (fixture 创建 2-3 个 org + user)

**B6 (1.5d, 1 commit) — Frontend E2E (5 关键流程)**:
- 写 Playwright spec (登录/上传/搜索/详情/导出)
- 跑真后端 (8000) + 真 DB + 真 redis + 真 qdrant
- **H 风险**: playwright CI 集成复杂, docker-compose + teardown workflow

**修复 PR (推后)**:
- A3+A4 fixture 改用真 user (避免后续 B 测 FK 失败)
- mcp_host anyio lifecycle
- run_recommendation_scan DB transaction abort

## 8. 回滚方法

```bash
git revert <B2 commit>
git checkout HEAD~1 -- apps/api/tests/mcp/integration/test_e2e_human_loop_b2.py
```

**回滚影响**:
- B2 测试消失
- 其他 E2E 不受影响
- 0 production 代码改动, **零风险**

## 9. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2 (B2 = Orchestrator 1.5d)
- Momus: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §2.1 (mock vs 真 LLM)
- 上站: B1 (Pipeline E2E, commit 2de20b3 + 12ea9c0)
- A3+A4 fixture 模式: `tests/mcp/integration/test_e2e_orchestrator_v1_4{a,b}.py`
- B1 mock 教训: `docs/mcp-v4-v1.4-b1-ship-report.md` §3.1
- ApprovalService: `app/services/approval_service.py` (create + resolve + list_pending)
- ScreeningAgent: `app/agents/screening_agent.py` (screen + needs_human_review)

**下一步**: 跳 B3 (Router 已 ship via A4) → B4 (Knowledge/RAG E2E 1d)
