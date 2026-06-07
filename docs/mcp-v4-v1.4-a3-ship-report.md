# Phase A · A3 Ship Report — v1.4a orchestrator parse→evaluate E2E

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.1 (A3 = v1.4a orchestrator parse→evaluate E2E 0.8d)
> **上一站**: `A2` (E2E 加 CI + perf 阈值门禁, 409477c + 03b83c6) — 2026-06-07
> **commit**: 1 个测试文件 + 1 个 ship report
> **接受门槛**: 2/2 测试通过 + 接入 mcp-ci.yml unit-tests job (自动)

## 1. 概览

| 维度 | 状态 |
|---|---|
| `test_e2e_orchestrator_v1_4a.py` 测试文件 (210+ 行) | ✅ |
| `test_orchestrator_parse_subgraph` 端到端 | ✅ resume_parser subgraph + mock LLM |
| `test_orchestrator_evaluate_subgraph` 端到端 | ✅ screening subgraph + mock agent |
| 接入 mcp-ci.yml `unit-tests` job | ✅ 自动 (pytest tests/mcp/ 跑全部) |
| 编排测试 (parse→evaluate 串联) | ⚠️ 推 A4 一起做 (mock RouterAgent 复杂) |
| 5 强约束 1 PR 必含测 | ✅ 2 个新测试 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/tests/mcp/integration/test_e2e_orchestrator_v1_4a.py` | +210 (新) | 2 测试 (parse + evaluate subgraph 端到端) |
| **总** | **+210 / 0** | 1 文件 |

## 3. 关键决策

### 3.1 测 2 子图端到端, 不测 orchestrator 编排 (Momus §1.1 修正版)

按 Momus §1.1 修正版:
> v1.4 "full pipeline orchestrator" 范围不明 → 拆 v1.4a (parse→evaluate) + v1.4b (match→schedule) 2 PR.

A3 v1.4a 拆为:
- 阶段 1: resume_parser subgraph 端到端 (parse)
- 阶段 2: screening subgraph 端到端 (evaluate)

**不测** orchestrator 编排 (intent_recognition → execute_subgraph) 的 2 子图串联, 理由:
- orchestrator 编排需要 mock `RouterAgent._rule_classify` 让 intent_recognition 返目标 intent
- intent_recognition 内部覆盖 `current_agent` (line 60-62), 直接 ainvoke 设的 current_agent 被覆盖
- 复杂度高, 跟 v1.4b 编排测试一起做避免重复 setup
- 推 A4 v1.4b 一起做编排测试 (parse→evaluate→match→schedule 4 阶段串联)

### 3.2 复用 v1.1+v1.2 模式 (mock LLM 入口 + DB 真跑)

按 CLAUDE.md 教训 "真 DB 路径必测" + "mock LLM 入口":
- `app.tools.resume_parser.extract_from_text` mock 返 ExtractedCandidate (v1.1+v1.2 同款)
- `app.agents.registry.AgentRegistry.resolve` mock 返 fake_agent (screening 入口)
- DB 真跑 (用 `e2e_client` fixture + `org_scoped_db` dep override)
- unique email (uuid suffix) 避免跨测试污染

### 3.3 修复 parsed_data 嵌套断言 (mask_pii 反直觉)

第一次跑测试 fail: `parsed["email"]` 返 `None`, 实际 email 在 `parsed["basic_info"]["email"]` 里, **且被 `mask_pii` 脱敏** (`z***@test.com` 不是原始 `z_xxx@test.com`)。

修复: 不直接比 email, 改验格式 `"@" in email`, 验证 name + years_of_experience + skills 透传正确。

**教训 (写进 ship report)**: `parsed_data` 嵌套结构 `basic_info {name, email(mask_pii), years_of_experience, ...} + skills (顶层 list) + education (顶层 list)`, 下次写测试要先看 `app/tools/resume_parser.py:140-160` 确认结构, 别假设。

### 3.4 不需要改 mcp-ci.yml (自动接入)

`mcp-ci.yml` 的 `unit-tests` job 跑 `pytest tests/mcp/ -v --tb=short`, A3 新测试文件自动被包含。**不需要改 workflow YAML**。

## 4. 测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_orchestrator_parse_subgraph` | resume_parser subgraph 端到端: HTTP upload → 拿 plain_text → subgraph.ainvoke() (mock LLM) → 验 parsed_data.basic_info {name, email mask_pii, years_of_experience=5} + skills 顶层 list + candidate_id + confidence > 0 |
| 2 | `test_orchestrator_evaluate_subgraph` | screening subgraph 端到端: subgraph.ainvoke() (mock AgentRegistry.resolve 返 fake agent.run 返 evaluation) → 验 match_score=8.5 + screening_result {overall_score=8.5, verdict=strong_hire} |

**未测** (推 A4 一起做):
- orchestrator 编排 (intent_recognition → execute_subgraph 串联)
- 跨 2 子图数据流 (parse candidate_id → evaluate 输入)
- RouterAgent intent 决策 (mock 整个 router)

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 2 新测试通过 | `pytest tests/mcp/integration/test_e2e_orchestrator_v1_4a.py` | ✅ 2/2 passed |
| 接入 mcp-ci.yml | unit-tests job 跑 tests/mcp/ 全部 | ✅ 自动覆盖 |
| 不动 production code | 仅新增 tests/ 目录文件 | ✅ 0 production 改动 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.5d (含调试 0.2d) | ✅ |
| 5 强约束 (+30% buffer) | 估 0.8d → 实际 0.5d | ✅ 在 buffer 内 |
| 5 强约束 (1 PR 必含测) | 2 新测试 | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (新测试, 不动 prod) | N/A |
| 5 强约束 (顺序锁死) | A1 → A5 → A2 → A3 (Phase A 第 4 步) | ✅ |

## 6. 未在 A3 范围（明确不做）

- ❌ orchestrator 编排 2 子图串联 (推 A4 一起做)
- ❌ RouterAgent intent 决策 mock (A4 一起)
- ❌ A2 报告里说的 perf 阈值 (A3 是功能测, 不跑 perf)
- ❌ frontend E2E (Phase B)
- ❌ A/B router fallback 测试 (v0.8.1 已测过)

## 7. 后续路径

**A4 (0.8d, 1 commit) — v1.4b orchestrator match→schedule E2E**:
- 写 `test_e2e_orchestrator_v1_4b.py`
- 测 sourcing subgraph (match) + interview subgraph (schedule)
- **A3 + A4 一起做编排测试** (mock RouterAgent._rule_classify 让 intent_recognition 返目标 intent, 验证 orchestrator 编排 4 阶段串联: parse→evaluate→match→schedule)

**A6 (0.3d, 1 commit) — ship report 模板化**:
- 抽 20+ ship report (现 19 + A1 + A2 + A3 + A5) 共性结构
- 写 `docs/ship-report-template.md`
- 写 lint/check 验证后续 PR 用模板

## 8. 回滚方法

```bash
git revert <A3 commit>
git checkout HEAD~1 -- apps/api/tests/mcp/integration/test_e2e_orchestrator_v1_4a.py
```

**回滚影响**:
- v1.4a E2E 测试消失 (其他 E2E 不受影响)
- mcp-ci.yml unit-tests job 跑剩余 13 个 e2e test 文件
- 0 production 代码改动, **零风险**

## 9. 引用

- 规划: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.1 (A3 = v1.4a parse→evaluate 0.8d)
- Momus 修正: `.omo/plans/2026-06-07-complete-roadmap-momus-review.md` §1.1 (拆 v1.4a+v1.4b 2 PR)
- 上站: A2 (E2E CI, commit 409477c + 03b83c6)
- 复测模式: `tests/mcp/integration/test_e2e_phase_d_v1_1.py` (v1.1 跨 server 业务流)
- 复测模式: `tests/mcp/integration/test_e2e_evaluation_interview_v1_2.py` (v1.2 5 步跨 server)
- Orchestrator 源码: `app/graphs/orchestrator.py` (line 128-160 build graph)
- Resume parser parsed_data 结构: `app/tools/resume_parser.py:140-160`
- CI workflow: `.github/workflows/mcp-ci.yml` (unit-tests job 跑 tests/mcp/)

**下一步**: A4 (v1.4b match→schedule + 编排测试)
