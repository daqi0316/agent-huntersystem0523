# Phase B · B1 Ship Report — AI Agent Pipeline E2E (mock LLM)

> **Ship 日期**: 2026-06-08
> **依据**: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2 (B1 = AI Agent Pipeline mock LLM 1.5d)
> **上一站**: `Fix-1` (lifespan 5min sleep + test_host_lifecycle 3 skip, b41a959 + 91b9510) — 2026-06-07
> **commit**: 1 个测试文件 + 1 个 ship report
> **接受门槛**: 3/3 测试通过 + 60+ 现有 E2E 不退化

## 1. 概览

| 维度 | 状态 |
|---|---|
| `test_e2e_pipeline_b1.py` 测试文件 (190+ 行) | ✅ |
| `test_pipeline_build_screening` 端到端 | ✅ 3 步正确添加 (parse/match/gate) |
| `test_pipeline_run_3_steps_with_mocked_llm` | ✅ mock LLM client, 验 3 步全跑 + final_output 含 3 步结果 |
| `test_pipeline_gate_failed_triggers_human_review` | ✅ gate_passed=false 路径 + needs_human_review=true 标记 |
| 60 个现有 E2E 不退化 | ✅ 63 passed (60 + 3 new) |
| 接入 mcp-ci.yml unit-tests job | ✅ 自动 (pytest tests/mcp/ 跑全部) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/tests/mcp/integration/test_e2e_pipeline_b1.py` | +196 (新) | 3 测试 (build + run 3 步 + gate failed human review) |
| **总** | **+196 / 0** | 1 文件 |

## 3. 关键决策

### 3.1 mock 路径: `app.agents.pipeline.get_llm_client` 而非 `app.llm.get_llm_client`

**踩坑**: PipelineAgent.parse_resume 用 `from app.llm import get_llm_client` 然后 `llm = get_llm_client()` 直接拿。
- 第一次试 `patch("app.llm.retry.llm_chat_with_retry", ...)` → 失败, LLM 仍真打 omlx (502)
- 第二次试 `patch("app.llm.get_llm_client", ...)` → 仍失败, 117s 卡死 (retry 5 次 × backoff)
- 第三次试 `patch("app.agents.pipeline.get_llm_client", ...)` → ✅ 0.03s 通过

**根因**: `from X import Y` 在 module load 时把 `Y = X.Y` 存到当前 module namespace. 后续 module 内部用 `Y()` 是用当前 module 名字, **不是** X.Y. patch 源头 X.Y 不会改变 module 已缓存的 Y 引用.

**正解**: patch module 内部 import 的名字 (即 `app.agents.pipeline.get_llm_client`).

**教训 (写进 ship report §3)**: mock 时**必须 patch 实际被调用时引用的名字**, 不仅是源头. 跟 v1.1+v1.2 模式不同 (那里 patch `app.tools.X.X` 就够, 因为测试只调那个 module 一次).

### 3.2 3 测覆盖: build + run + gate_failed

按 Momus §2.1 修正版 "加 3 测 (每组件 1 测)":
- 测 1: `test_pipeline_build_screening` — 验工厂方法创建 3 步
- 测 2: `test_pipeline_run_3_steps_with_mocked_llm` — happy path (gate 通过)
- 测 3: `test_pipeline_gate_failed_triggers_human_review` — sad path (gate 失败 + 需人工)

测 2 + 测 3 一起覆盖"是否需要人工复审" 业务决策, 不止验技术细节.

### 3.3 真 LLM E2E 推 Phase E (手动 + staging)

按 Momus §2.1 修正版:
> 真 LLM E2E 推 Phase E (manual + staging).

B1 不测真 LLM, 原因:
- 真 LLM 5-30s/调用, 3 步 15-90s, CI runner 限速 + token 成本
- mock LLM 入口已覆盖 3 步 + final_output 逻辑
- 真 LLM 测应推 Phase E 手动 + staging 环境

## 4. 测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_pipeline_build_screening` | 验 `build_screening_pipeline()` 工厂方法返 3 步 (parse/match/gate) |
| 2 | `test_pipeline_run_3_steps_with_mocked_llm` | mock LLM client 返 3 不同 JSON, 验 pipeline.run() 完成 3 步 + final_output 含 parsed_resume + match_result + gate_result + final_score + gate_passed + needs_human_review |
| 3 | `test_pipeline_gate_failed_triggers_human_review` | mock LLM 返 gate_passed=false, 验 pipeline 不阻断但 final_output.gate_passed=False + needs_human_review=True + issues 含"经验不足" |

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 3 新测试通过 | `pytest tests/mcp/integration/test_e2e_pipeline_b1.py` | ✅ 3/3 passed |
| 60 现有 E2E 不退化 | `pytest tests/mcp/integration/ --ignore=test_host_lifecycle` | ✅ 63 passed |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.3d (含 mock 路径调试 0.2d) | ✅ |
| 5 强约束 (+30% buffer) | 估 1.5d → 实际 0.3d | ✅ 在 buffer 内 |
| 5 强约束 (1 PR 必含测) | 3 新测试 | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (新测试, 不动 prod) | N/A |
| 5 强约束 (顺序锁死) | B1 = Phase B 第 1 步 | ✅ |
| 5 强约束 (量化 KPI) | 3/3 测 + 0.03s 跑完 + 60 E2E 不退化 | ✅ 3 KPI |

## 6. 未在 B1 范围（明确不做）

- ❌ 真 LLM E2E 测 (推 Phase E 手动 + staging)
- ❌ mock 失败/异常 路径测 (parse 失败抛 → pipeline 中断? 待验)
- ❌ performance 测 (Pipeline 3 步 < X 秒, 待推后续 perf 测)
- ❌ run_recommendation_scan DB transaction abort 根因 (Fix-1 推后, 独立 PR)
- ❌ mcp_host test cleanup (Fix-1 推后, 独立 PR)

## 7. 后续路径

**B2 (0.8d, 1 commit) — AI Agent Orchestrator E2E**:
- 写 `test_e2e_orchestrator_b2.py`
- 测 orchestrator 编排 screening subgraph + 入参 (candidate_id + job_id)
- mock `app.agents.registry.AgentRegistry.resolve` 返 fake screening agent
- 复用 A3+A4 fixture 模式

**B3 (0.5d, 1 commit) — AI Agent Router E2E**:
- 写 `test_e2e_router_b3.py`
- 测 RouterAgent 决策 (mock `_rule_classify`)
- 验 routing 到正确 subgraph

**B4 (1.2d, 1 commit) — Knowledge/RAG E2E (Qdrant)**:
- 写 `test_e2e_knowledge_b4.py`
- 测 upload → query → cite 端到端
- mock LLM cite 格式

**B5 (1d, 1 commit) — Auth/Org E2E (5-8 隔离 case)**:
- 写 `test_e2e_auth_org_b5.py`
- 测同 org/跨 org/super_admin/org 切换 多场景

**B6 (2d, 1 commit) — Frontend E2E (5 关键流程)**:
- 写 Playwright spec (登录/上传/搜索/详情/导出)
- 跑真后端 (8000) + 真 DB + 真 redis + 真 qdrant
- **H 风险**: playwright CI 集成复杂, docker-compose + teardown workflow

**修复 PR (推后)**:
- mcp_host anyio lifecycle
- run_recommendation_scan DB transaction abort

## 8. 回滚方法

```bash
git revert <B1 commit>
git checkout HEAD~1 -- apps/api/tests/mcp/integration/test_e2e_pipeline_b1.py
```

**回滚影响**:
- B1 测试消失
- 其他 E2E 不受影响
- 0 production 代码改动, **零风险**

## 9. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2 (B1 = Pipeline mock LLM 1.5d)
- Momus: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §2.1 (mock vs 真 LLM)
- 上站: Fix-1 (lifespan 5min sleep + test_host_lifecycle 3 skip, b41a959 + 91b9510)
- 复测模式: `tests/mcp/integration/test_e2e_orchestrator_v1_4a.py` (A3 v1.4a mock agent)
- Pipeline 源码: `app/agents/pipeline.py` (3 步: parse/match/gate)
- Mock 关键: `app.llm.retry.llm_chat_with_retry` + `app.agents.pipeline.get_llm_client`

**下一步**: B2 (AI Agent Orchestrator E2E 0.8d)
