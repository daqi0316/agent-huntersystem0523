# Phase A · A4 Ship Report — v1.4b orchestrator match→schedule E2E + bug fix

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.1 (A4 = v1.4b orchestrator match→schedule E2E 0.8d)
> **上一站**: `A3` (v1.4a parse→evaluate E2E, d431bb9 + ffed6f3) — 2026-06-07
> **commit**: 1 个测试文件 + 1 个 orchestrator bug fix + 1 个 ship report
> **接受门槛**: 3/3 v1.4b 测试通过 + 60+ 现有 E2E 不退化

## 1. 概览

| 维度 | 状态 |
|---|---|
| `test_e2e_orchestrator_v1_4b.py` 测试文件 (3 测试) | ✅ |
| `test_orchestrator_match_subgraph` 端到端 | ✅ sourcing subgraph + mock agent |
| `test_orchestrator_schedule_subgraph` 端到端 | ✅ interview subgraph + mock agent |
| `test_orchestrator_full_pipeline` 4 阶段编排 | ✅ parse→evaluate→match→schedule |
| **Orchestrator bug fix** (`execute_subgraph` history 累加) | ✅ **CLAUDE.md 教训"找 hidden bug 价值"应验** |
| 60 个现有 E2E 测试不破坏 | ✅ (test_host_lifecycle 3 个预存在 fail, 跟我无关) |
| 接入 mcp-ci.yml unit-tests job | ✅ 自动 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/tests/mcp/integration/test_e2e_orchestrator_v1_4b.py` | +256 (新) | 3 测试 (match + schedule + 4 阶段编排) |
| `apps/api/app/graphs/orchestrator.py` | +3 / -1 | 修 `execute_subgraph` history 累加 (production bug fix) |
| **总** | **+259 / -1** | 2 文件 |

## 3. 关键决策

### 3.1 A4 测试发现 orchestrator 历史 bug (E2E 价值证明)

**Bug**: `app/graphs/orchestrator.py:execute_subgraph` 写 `update["execution_history"] = [entry]` —— **覆盖**而非**累加**。

**影响**: orchestrator 跑 multi-invoke 编排时 (4 阶段串联), `execution_history` 只保留最后一次 invoke 的 entry, 之前 3 阶段的历史全丢。`/tasks/{id}/timeline` 端点跟 `execution_history` 联动, UI 上看到 1 个 agent 而不是 4 个, **诊断 / 排查 / 审计都失真**。

**触发**: A4 编排测试 `test_orchestrator_full_pipeline` 跑 4 次 ainvoke (parse→evaluate→match→schedule), 验 `execution_history` 含 4 entry — fail, 实际只 1 entry `['interview']`。

**修复**: `update["execution_history"] = state.get("execution_history") or [] + [entry]` (读 state 现有 history, append 当前 entry)。

**验证**: 修完 3/3 测试通过, 60 个现有 E2E 不退化 (test_host_lifecycle 3 个预存在 fail 跟我无关, stash 验证过)。

**这正是 CLAUDE.md 5 强约束期望的**:
- §9 教训 #1: "E2E 找 hidden bug 价值证明" (v1.1 找 v0.4d bug, v1.2 找 4 bug) — A4 找 1 bug
- A3 + A4 编排测试是 **pre-mortem 验证**, 不是写完就完事

### 3.2 编排测试设计: 4 次 ainvoke 串联

**单次 ainvoke 行为**: `intent_recognition` → `execute_subgraph` (1 个) → `create_snapshot` → END。**不循环 multi-intent**。

**测 4 阶段串联**:
- 4 次 ainvoke, 每次 mock `RouterAgent._rule_classify` 返下一个 intent (按 intent_sequence 循环)
- `state` 在 4 次间累积 (LangGraph checkpointer 持久化到 thread_id)
- 验 `execution_history` 含 4 entry + 4 个子图 state 都设置

**为什么不测 1 次 ainvoke multi-intent**:
- graph 设计就是 single-intent-per-invoke, 改 graph 改生产代码 = A4 范围外
- 1 次 multi-intent 是另一个 PR (可能跟 v0.7 multi_intent_router 重复)

### 3.3 mock RouterAgent 入口选择

**3 个 mock 候选**:
1. `RouterAgent._rule_classify` (sync, 返 `(intent, confidence)`) — **选这个**
2. `RouterAgent.classify` (async, 返 intent)
3. `AgentRegistry.resolve("router")` (高层)

**选 1**: `intent_recognition` 内部 `router._rule_classify(text)` (line 57), mock 这个最稳, 避免 mock 整个 router 实例。

### 3.4 test_host_lifecycle 3 个预存在 fail (不修)

**fail 现象**: `expected 1 connected, got 5` + `Attempted to exit cancel scope in a different task` (anyio).

**根因 (推测)**: mcp_host 用 anyio task 管理 + 测试 mock 计数硬编码, 跟 anyio task lifecycle 不兼容。

**不修, 理由** (按 CLAUDE.md "Bugfix Rule"):
- 预存在 fail, 不是 A4 引入 (git stash 验证)
- 修 mcp_host 涉及 anyio 重构, 跟 A4 范围不同
- 推 Phase B 修复 PR (跟 §4.1 uvicorn hang 死, 5 已知问题合并修)

## 4. 测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_orchestrator_match_subgraph` | sourcing subgraph 端到端: mock AgentRegistry.resolve 返 fake_search agent → 验 candidates_found list 含 2 candidate + match_score |
| 2 | `test_orchestrator_schedule_subgraph` | interview subgraph 端到端: mock agent 返 fake_schedule → 验 interview_scheduled=True + feedback.interview_id + status |
| 3 | `test_orchestrator_full_pipeline` | 4 阶段编排: 4 次 ainvoke + mock RouterAgent._rule_classify 按 sequence 返 4 intent + mock 3 个 agent (screening/sourcing/interview) + mock LLM extract_from_text → 验 4 子图 state + execution_history 4 entry |

**未测** (推后续):
- orchestrator multi-intent 单次 ainvoke (graph 设计不支持, 需改 graph)
- orchestrator 失败回滚 (subgraph error 后 state 怎么清理)
- checkpointer 持久化 (PostgresSaver vs MemorySaver)

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 3 新测试通过 | `pytest tests/mcp/integration/test_e2e_orchestrator_v1_4b.py` | ✅ 3/3 passed |
| Orchestrator bug 修复 | test 3 execution_history 含 4 entry (修复前 fail) | ✅ 修复后通过 |
| 60 现有 E2E 不破坏 | `pytest tests/mcp/integration/ --ignore=test_host_lifecycle` | ✅ 60 passed |
| test_host_lifecycle 3 预存在 fail | git stash 验证 | ✅ 跟我无关 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.7d (含 bug fix) | ✅ |
| 5 强约束 (+30% buffer) | 估 0.8d → 实际 0.7d | ✅ |
| 5 强约束 (1 PR 必含测) | 3 新测试 + 1 bug fix | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (orchestrator bug fix 严格累加, 不改逻辑) | N/A |
| 5 强约束 (顺序锁死) | A1 → A5 → A2 → A3 → A4 (Phase A 第 5 步) | ✅ |

## 6. 未在 A4 范围（明确不做）

- ❌ orchestrator multi-intent 单次 ainvoke (graph 改造, 推后续 PR)
- ❌ test_host_lifecycle 3 预存在 fail (anyio 重构, 推 Phase B)
- ❌ checkpointer 持久化 E2E (PostgresSaver 需 CI DB, 推 A2 后续)
- ❌ orchestrator 失败回滚 (graph 改造, 推后续 PR)
- ❌ A5 perf 阈值在 A4 新测试上跑 (A4 是功能测, 不跑 perf)

## 7. 后续路径

**A6 (0.3d, 1 commit) — ship report 模板化**:
- 抽 21+ ship report (现 19 + A1+A2+A3+A4+A5) 共性结构
- 写 `docs/ship-report-template.md`
- 写 lint/check 验证后续 PR 用模板

**Phase B 修复 PR (推后)**:
- test_host_lifecycle anyio 重构
- uvicorn hang 死 (A5 §4.1)
- orchestrator multi-intent graph 改造

## 8. 回滚方法

```bash
git revert <A4 commit>
# 改动 2 文件
git checkout HEAD~1 -- \
  apps/api/tests/mcp/integration/test_e2e_orchestrator_v1_4b.py \
  apps/api/app/graphs/orchestrator.py
```

**回滚影响**:
- v1.4b E2E 测试消失
- **orchestrator bug 回归**: multi-invoke 时 execution_history 覆盖 (用户 UI 上 timeline 只看到最后 1 个 agent)
- 影响: `/tasks/{id}/timeline` 端点数据失真
- 风险: M (生产 bug 回归, 但 60 E2E 还能过, 用户感知弱)

## 9. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.1 (A4 = v1.4b match→schedule 0.8d)
- Momus: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §1.1 (拆 v1.4a+v1.4b 2 PR)
- 上站: A3 (v1.4a parse→evaluate E2E, d431bb9 + ffed6f3)
- Bug fix: `app/graphs/orchestrator.py:execute_subgraph` line 88-95 (历史覆盖 bug, A4 E2E 发现)
- 编排测试设计: 4 次 ainvoke + mock RouterAgent._rule_classify (line 124)
- 子图源码: `app/graphs/agents/sourcing.py` + `interview.py`
- 复测模式: `tests/mcp/integration/test_e2e_orchestrator_v1_4a.py` (A3 v1.4a 复用同款 fixture)

**下一步**: A6 (ship report 模板化)
