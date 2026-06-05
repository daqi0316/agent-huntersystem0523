# Plan: approval_status enum 写入冲突修复（工业级）

## 0. Context

**症状**：Dashboard 点击"进行中面试/本月入职"报 500。
**根因**：`SAEnum(PythonEnumClass, name=...)` 写库用 enum `name`（大写），
但 PostgreSQL `approval_status` enum label 是小写（`pending/approved/...`），
cast 失败 → `InvalidTextRepresentationError`。

**调用链**：
Dashboard → `<ApprovalCountdown>` → `GET /api/v1/human-loop/pending` →
`HumanLoopAgent.get_pending_proposals()` → `ApprovalService.list_pending()` →
`expire_pending()` → `UPDATE approvals SET status='EXPIRED'::approval_status` → 500

## 1. 根因（已核实）

| enum | DB label | Model enum class | values_callable | 状态 |
|---|---|---|---|---|
| `approval_status` | `pending/...` 小写 | `PENDING=pending` 等 | ❌ 缺 | 🔴 修 |
| `recommendation_type` | `candidate_job_match/...` 小写 | `CANDIDATE_JOB_MATCH=...` | ❌ 缺 | 🔴 修 |
| `interview_round` | 未建表 | `R1=phone_screen` | ❌ 缺 | 🟡 防 |
| `evaluation_verdict` | 未建表 | `STRONG_HIRE=strong_hire` | ❌ 缺 | 🟡 防 |
| `candidate_status` | 小写 | `ACTIVE=active` | ✅ 有 | ✅ |
| `interview_status/type` | 大写 | 大写 | — | ✅ |
| `application_status/job_status/user_role` | 大写 | 大写 | — | ✅ |
| `operation_status/error_category` | — | — | — | 用 `String` 不是 `SAEnum` |

**核实证据**：
- `SELECT 'PENDING'::approval_status` → **FAILS** (大写不匹配)
- `SELECT 'pending'::approval_status` → 成功（小写匹配）
- `SELECT enum_range(NULL::approval_status)` → `[pending,approved,rejected,expired,cancelled]`
- `approvals` 表为空，无遗留数据

## 2. 修复策略

**核心解药**：所有"value 是小写、name 是大写"的 Python `str` enum，
SQLAlchemy 列定义必须加 `values_callable=lambda x: [e.value for e in x]`，
确保写库用 value，与 DB label 一致。

**封装为工厂**：新建 `app/models/_base.py::enum_column()`，
**所有 model 统一调用**，杜绝再次遗漏。

## 3. 计划

### 阶段 A：根因修复（一致性）

| 步骤 | 文件 | 改动 | 验证 |
|---|---|---|---|
| A.1 | `app/models/_base.py`（新建） | `enum_column(py_enum, name)` 工厂 | 导入不报错 |
| A.2 | `app/models/approval.py` | `approval_status` 改用 `enum_column` | lsp 干净 |
| A.3 | `app/models/recommendation.py` | `recommendation_type` 改用 | lsp 干净 |
| A.4 | `app/models/interview_evaluation.py` | `interview_round` + `evaluation_verdict` 改用 | lsp 干净 |
| A.5 | 跑现有 mock 测试 | `pytest tests/test_approval_service.py -v` | 0 回归 |

### 阶段 B：服务层隔离

| 步骤 | 文件 | 改动 | 验证 |
|---|---|---|---|
| B.1 | `app/services/approval_service.py` | `list_pending` 内 `expire_pending` 失败时 `log + publish event`，**不静默吞** | lsp 干净 |

### 阶段 C：集成测试 + 验证

| 步骤 | 文件 | 改动 | 验证 |
|---|---|---|---|
| C.1 | `tests/test_models_enum_integration.py`（新建） | 真 DB round-trip：写 model → raw SQL 读回 → 断言是小写 value | 新测试通过 |
| C.2 | 跑集成测试 | `pytest tests/test_models_enum_integration.py -v` | 通过 |
| C.3 | 跑全套 | `pytest tests/ --cov=app` | 全绿，覆盖率不降 |
| C.4 | 手动验证 | `curl /api/v1/human-loop/pending` + 创建 approval + expire | HTTP 200，DB status 小写 |

## 4. 成功标准（Done Definition）

- ✅ 后端 `GET /api/v1/human-loop/pending` 返回 200 + JSON 数组（哪怕空）
- ✅ DB `approvals.status` 实际值是小写（`pending/expired/...`）
- ✅ `pytest tests/test_approval_service.py` 268 行 mock 测试 0 失败
- ✅ `pytest tests/test_models_enum_integration.py` 新测试全绿
- ✅ `pytest tests/ --cov=app` 全套通过，覆盖率 ≥ 50%
- ✅ `expire_pending` 失败时**有日志 + 有 event**，不静默

## 5. Out of Scope（明确不做）

- ❌ 前端 `ApprovalCountdown` 容错（独立 task）
- ❌ `_pending_purge_all` bug 修复（不相关）
- ❌ pre-commit / CI 校验（独立 task）
- ❌ `operation_log`（用 `String` 不是 `SAEnum`，无问题）
- ❌ Alembic 迁移（DB label 已对，model 改完直接写）
- ❌ 一致性 enum（`interview_status/type` 等 name==value 大写）— 不动

## 6. 回滚

```bash
git revert <commit>  # model 改回原 SAEnum(...) 不带 values_callable
# DB 不需要回滚（label 仍然小写对）
# 重启后原 bug 复现 — 确认是 enum 写库问题
```

## 7. 风险

- **数据风险**：无（approvals 表空，DB label 已对）
- **回归风险**：极低（只改 model 写库行为，service / API / 序列化都不变）
- **影响半径**：仅 enum 写入路径，影响 `approvals` / `recommendations` / `interview_evaluations` 表
