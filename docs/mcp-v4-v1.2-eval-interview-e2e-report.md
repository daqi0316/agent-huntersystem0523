# v1.2 Ship Report — 跨 3 Server E2E + 4 Hidden Production Bugs

> **报告日期**: 2026-06-07
> **依据**: v0.8.2 ship report §7 (v1.2 1d, 实际 2-3d 因 E2E 暴露 hidden bugs)
> **范围**: candidate → job → interview → evaluation → report 5 步跨 3 server E2E
> **意外产出**: 4 个 v0.3 隐藏 production bug 一并修

## 1. 范围 vs 实际

| 计划 | 实际 | 备注 |
|---|---|---|
| 1 Python E2E (5 步跨 3 server) | ✅ | test_e2e_evaluation_interview_v1_2.py |
| 不动 production code | ❌ | **改 5 处** (handler + model + 2 migration) |
| 1d | **2-3d** | E2E 暴露 4 hidden bug, 原子修 |

## 2. v0.3 4 Hidden Bugs (Momus §3 关注点)

### 2.1 Bug 1: schedule_interview handler 缺 application_id

**症状**: `interviews.application_id` 是 NOT NULL, 但 `_handle_schedule_interview` 不接受 application_id, service 层 `application_id = slot.get("application_id", "")` 永远空, INSERT fail.

**修复**: handler 加 `application_id=""` 参数 + slot 字典加 `application_id` 字段:
```python
async def _handle_schedule_interview(candidate_id="", job_id="", scheduled_time="", notes="", application_id=""):
    slot = {
        "type": "video",
        "scheduled_at": ...,
        "notes": notes,
        "application_id": application_id,  # 新增
    }
```

### 2.2 Bug 2: interview_evaluations 表根本没建

**症状**: `InterviewEvaluation` model 存在 (v0.3 加), 但 Alembic migration 漏建. 真 DB 路径 INSERT 抛 `UndefinedTableError`.

**修复**: 建 `v1_2_interview_evaluations` migration:
- 表结构 (id, interview_id FK, round, verdict, scores, dimensions, ...)
- enum 类型: interview_round (R1=phone_screen, R2=technical, R3=behavioral, R4=final) + evaluation_verdict (strong_hire/hire/consider/pass)
- FK 到 interviews.id (CASCADE delete)
- index on interview_id

### 2.3 Bug 3: 多 Alembic heads (p6_12 + v1_2)

**症状**: 加 v1.2 migration 后, alembic 有 2 heads (`p6_12_csm_task_fix` + `v1_2_interview_evaluations`), `alembic upgrade head` 失败.

**修复**: 建 merge migration `merge_p6_12_v1_2` (`down_revision` 设为 tuple).

### 2.4 Bug 4: InterviewEvaluation.interview_id 类型 mismatch

**症状**: model 声明 `String(36)` 但 DB 列是 `uuid` (因为 FK 到 interviews.id 是 uuid). `INSERT ... VALUES ($1::VARCHAR)` 报 `DatatypeMismatchError: column is uuid but expression is character varying`.

**修复**: model 改用 `UUID(as_uuid=False)` 仿 interviews.id 模式 (DB 类型 uuid, Python 类型 str):
```python
interview_id: Mapped[str] = mapped_column(
    UUID(as_uuid=False),  # 改: String(36) → UUID(as_uuid=False)
    ForeignKey("interviews.id", ondelete="CASCADE"),
    nullable=False, index=True,
)
```

## 3. E2E 设计 (Momus §3 关注点)

### 3.1 5 步业务流

```
HTTP POST /api/v1/resume/upload-resume  →  plain_text
  ↓ (mock LLM)
mcp-resume parse_resume  →  candidate_id
  ↓
mcp-job create_job  →  job_id
  ↓
mcp-application create_application  →  application_id  (v1.2 新增 step, 修 Bug 1)
  ↓
mcp-interview schedule_interview  →  interview_id
  ↓
mcp-evaluation save_evaluation  →  evaluation_id
  ↓
mcp-evaluation generate_evaluation_report  →  含 R1 评估的汇总
```

### 3.2 关键决策

| 决策 | 选 | 理由 |
|---|---|---|
| Mock LLM | patch `extract_from_text` | v1.1 模式, 避免真 LLM 5-10s 慢 |
| application_id 传递 | 显式 param, 不用隐式 auto-create | 调用方可控, 避免隐式副作用 |
| E2E 测 1 vs 多 | 1 测 (5 步全跑) | 跨 3 server 业务流, 不拆 step |
| Bug 修法 | 原子 (handler + model + migration 同 PR) | 拆 PR 增 merge 风险 |

### 3.3 测枚举值发现

`InterviewRound.R1` enum 值是 `"phone_screen"` (model 定义), 不是 `"R1"`. Test 第一次 assert 失败, 改 assert 匹配 enum 值.

## 4. 测试结果

### 4.1 v1.2 新测 (1/1 pass)

```
tests/mcp/integration/test_e2e_evaluation_interview_v1_2.py::test_e2e_candidate_interview_evaluation_flow PASSED
======================== 1 passed, 4 warnings in 0.14s ========================
```

### 4.2 累计回归 (63/63 pass)

```
test_skill_cli_v0_7_2 (4) + test_sentry_traces_v1_0b_1 (4)
+ test_datetime_v1_0b_utc + test_skill_cli + test_skill_mgr_v0_7
+ test_resume_parser_v0_6c1_force_diff (6) + test_resume_parser_v0_6c_force (5)
+ test_resume_parser_v0_6b_ws + test_resume_parser_v0_6a_async
+ test_resume_parser_v0_5b_retry (4) + test_resume_parser_v0_4d
+ test_e2e_phase_d_v1_1 (2) + test_search_skills_filter_v1_1_1 (1)
+ test_e2e_evaluation_interview_v1_2 (1)
======================== 63 passed, 8 warnings in 3.58s ========================
```

### 4.3 Health-check (13/14, 1 限流 known)

| Step | 状态 | 备注 |
|---|---|---|
| 基础设施 (5432/6379/6333/9000) | ✅ | docker 全 LISTEN |
| uvicorn 8000 | ✅ | — |
| POST /auth/login | ❌ | rate_limited (v0.8+E2E 已知交互) |
| GET /auth/me (cascade) | ❌ | cascade from login |
| GET /login 200 | ✅ | — |
| verify-login-e2e.ts (cascade) | ❌ | cascade |
| /auth/wechat/qrcode + mock-login | ✅ | — |
| /auth/me 微信 | ✅ | — |
| 60 并发触发限流 429 | ✅ | — |
| 限流中间件 | ✅ | — |
| MCP CI 守门 | ✅ | — |

**Known issue**: health-check 自身 step 8 触发 60 并发, 下次跑 step 3 必撞 60s 限流. 不是 v1.2 引入的 regression.

## 5. 关键文件

| 文件 | 类型 | 行数 | 说明 |
|---|---|---|---|
| `apps/api/app/tools/interview.py` | 改 | +10 | handler 加 application_id param (Bug 1) |
| `apps/api/app/models/interview_evaluation.py` | 改 | +2 | interview_id String→UUID(as_uuid=False) (Bug 4) |
| `apps/api/alembic/versions/v1_2_interview_evaluations.py` | 新 | 90 | 建表 migration (Bug 2) |
| `apps/api/alembic/versions/merge_p6_12_v1_2.py` | 新 | 25 | merge 2 heads (Bug 3) |
| `apps/api/tests/mcp/integration/test_e2e_evaluation_interview_v1_2.py` | 新 | 173 | 1 E2E 5 步跨 3 server |
| `.omo/plans/v1.2-eval-interview-e2e.md` | 新 | 100+ | 实施计划 |
| `docs/mcp-v4-v1.2-eval-interview-e2e-report.md` | 新 | (本文) | ship report |

## 6. 决策

✅ **跨 3 server E2E 验证通过 + 4 hidden production bug 修**

**v1.2 价值**:
- **生产 bug 修复**: v0.3 隐藏 4 个 bug, 真 DB 路径会失败
  - Bug 1: schedule_interview 缺 application_id (handler)
  - Bug 2: interview_evaluations 表缺失 (migration)
  - Bug 3: 多 alembic heads (migration 管理)
  - Bug 4: InterviewEvaluation.interview_id 类型 mismatch (model)
- **业务流验证**: candidate → job → application → interview → evaluation → report 跨 3 server 端到端跑通
- **E2E 价值证明**: 又是 E2E 找到 hidden bug (v1.1 找到 v0.4d UUID bug, v1.2 找到 4 个)

## 7. 累计 MCP v4 Follow-ups 总结

| PR | 估时 | 实际 | 测 | 关键产出 |
|---|---|---|---|---|
| v1.0b.1 | 0.1d | 0.1d | +4 | SENTRY key typo + 兼容 shim |
| v0.7.2 | 0.2d | 0.2d | +4 | skill_cli 鉴权 + 审计 |
| v0.8.1 | 0.3d | 0.3d | 0 | Popen+psutil 真 fd/memory |
| v1.1 | 1.5d | 1.5d | +2 | Phase D E2E + v0.4d UUID bug 修 |
| v1.1.1 | 0.2d | 0.2d | +1 | skills filter 真生效 |
| v0.8.2 | 0.3d | 0.3d | 0 | long-running scenario 推翻 v0.8.1 误判 |
| **v1.2** | 1d | 2-3d | +1 | 5 步跨 3 server E2E + 4 hidden bug |
| **合计** | **3.6d** | **4.6-5.6d** | **+12** | **17 ship reports** |

## 8. 后续路径

| 项 | 估时 | 优先级 |
|---|---|---|
| **v1.3**: 测 full pipeline orchestrator (需 GraphState 重构) | 1.5d | 低 |
| 健康检查限流 mitigation | 0.2d | 低 (已知 issue) |
| 修 v0.4d 类似 type mismatch 扫全 models | 0.5d | 中 (v1.2 暴露同类) |
| 评估多轮次 R1+R2+R3 测 | 0.3d | 低 |

## 9. 引用

- v1.2 plan: `.omo/plans/v1.2-eval-interview-e2e.md`
- v0.8.2 ship report: `docs/mcp-v4-v0.8.2-load-test-report.md` §7
- v1.1 ship report: `docs/mcp-v4-v1.1-phase-d-e2e-report.md` (类似 hidden bug 模式)
- handler: `apps/api/app/tools/interview.py:26-40`
- model: `apps/api/app/models/interview_evaluation.py:34-36`
- migration: `apps/api/alembic/versions/v1_2_interview_evaluations.py`
- merge migration: `apps/api/alembic/versions/merge_p6_12_v1_2.py`
- E2E: `apps/api/tests/mcp/integration/test_e2e_evaluation_interview_v1_2.py`
- v0.4d UUID bug fix (类似模式): commit `145d228`
