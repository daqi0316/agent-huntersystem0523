# v1.3 Ship Report — Type Mismatch 扫全 Models + Pre-commit 防御检查

> **报告日期**: 2026-06-07
> **依据**: v1.2 ship report §8 (option 1, 0.5d, 主动防 v0.4d/v1.2 Bug 4)
> **范围**: 扫全 models 找 UUID/varchar mismatch + 修 + 加防御检查

## 1. 范围 vs 实际

| 计划 | 实际 | 备注 |
|---|---|---|
| 扫全 models UUID/varchar mismatch | ✅ | 找 1 真 mismatch (recommendation.py) |
| 修 + 加 1 测 | ✅ | 2 新测覆盖新 check |
| 0.5d | **0.3d** | 比估时快 (只 1 mismatch) |
| 加防御 pre-commit check | ✅ | STRING36_FK_UUID_PATTERN + 更新 check_model_patterns.py |

## 2. v1.2 暴露的同类 Bug 模式

v1.2 E2E 找到 `InterviewEvaluation.interview_id` 是 `String(36)` 但 DB 是 uuid (`interviews.id` 类型 mismatch). v1.3 主动扫所有 models 防再发.

## 3. 扫全结果 (8 UUID + 7 FK 目标)

### 3.1 DB 真实类型确认 (扫 6 核心表)

| 表 | id 真实 DB 类型 |
|---|---|
| candidates | **uuid** |
| job_positions | **uuid** |
| applications | **uuid** |
| interviews | **uuid** |
| users | character varying |
| operation_logs | character varying |

### 3.2 Model 中所有 `UUID(as_uuid=False)` 列 (8 个)

| Model | 列 | FK 目标 | DB 真类型 | 状态 |
|---|---|---|---|---|
| candidate | id (PK) | — | uuid | ✅ |
| application | id (PK) | — | uuid | ✅ |
| application | candidate_id | candidates.id | uuid | ✅ |
| application | job_id | job_positions.id | uuid | ✅ |
| interview | id (PK) | — | uuid | ✅ |
| interview | candidate_id | candidates.id | uuid | ✅ |
| interview | application_id | applications.id | uuid | ✅ |
| job_position | id (PK) | — | uuid | ✅ |
| interview_evaluation | interview_id | interviews.id | uuid | ✅ (v1.2 修) |
| operation_log | superseded_by | (无 FK) | uuid | ✅ |

**结论**: 8 `UUID(as_uuid=False)` 列全对 (DB 类型 = uuid).

### 3.3 找 1 真 mismatch: recommendation.py

```
candidate_id: String(36), ForeignKey("candidates.id")    -- DB 是 uuid
job_id: String(36), ForeignKey("job_positions.id")      -- DB 是 uuid
```

**修法**: 改用 `UUID(as_uuid=False)` 仿 application/interview pattern.

### 3.4 防再发: pre-commit check 加 STRING36_FK_UUID_PATTERN

`scripts/check_model_patterns.py` 加第 3 条规则:
- 扫所有 `ALL_MODEL_FILES` 找 `String(36)` + `ForeignKey("interviews|candidates|applications|job_positions.id"...)` 跨行模式
- 命中即 fail pre-commit
- 修正指南: `String(36) FK uuid 表 -> UUID(as_uuid=False)`

**也更新 UUID_SCAN_FILES**: 移除 `recommendation.py` (其 FK 目标 DB 是 uuid, `UUID(as_uuid=False)` 是合法类型, 不应纳入禁止).

## 4. 防御检查 3 条规则汇总

| 规则 | 检测 | 修正 |
|---|---|---|
| BARE_SAENUM | `SAEnum(<lowercase-enum>, name=...)` 裸调用 | `enum_column(EnumClass, name)` |
| UUID_AS_FALSE | `UUID(as_uuid=False)` 在 approval/command_audit_log | `String(36)` (DB 是 varchar) |
| **STRING36_FK_UUID (v1.3 新)** | `String(36)` FK 到 uuid 表 | `UUID(as_uuid=False)` |

**扫 16 SAEnum + 2 UUID + 16 String36 FK**, 全 0 违规.

## 5. 测试

### 5.1 v1.3 新测 (2/2 pass)

`apps/api/tests/test_check_model_patterns_v1_3.py`:
- `test_check_model_patterns_catches_string36_fk_to_uuid`: 写含 String(36) FK 到 candidates.id 的"违规"代码到 /tmp, 验 check 抓到
- `test_recommendation_model_passes_check`: 验修后 recommendation.py 0 违规 + 不在 UUID_SCAN_FILES

### 5.2 累计回归 (65/65 pass)

```
test_check_model_patterns_v1_3 (2) [新]
+ test_skill_cli_v0_7_2 (4) + test_sentry_traces_v1_0b_1 (4)
+ test_datetime_v1_0b_utc + test_skill_cli + test_skill_mgr_v0_7
+ test_resume_parser_v0_6c1_force_diff (6) + test_resume_parser_v0_6c_force (5)
+ test_resume_parser_v0_6b_ws + test_resume_parser_v0_6a_async
+ test_resume_parser_v0_5b_retry (4) + test_resume_parser_v0_4d
+ test_e2e_phase_d_v1_1 (2) + test_search_skills_filter_v1_1_1 (1)
+ test_e2e_evaluation_interview_v1_2 (1)
======================== 65 passed, 8 warnings in 3.11s ========================
```

### 5.3 Health-check (12/13, 1 限流 known)

v0.8+E2E 已知交互. 修 `pre-commit-config.yaml` 自动跑 check_model_patterns.py (已有 hook, v1.3 加新规则).

## 6. 关键文件

| 文件 | 类型 | 行数 | 说明 |
|---|---|---|---|
| `apps/api/app/models/recommendation.py` | 改 | +2 | candidate_id + job_id 改 UUID(as_uuid=False) |
| `scripts/check_model_patterns.py` | 改 | +20 | 加 STRING36_FK_UUID_PATTERN + 移除 recommendation.py from UUID_SCAN_FILES |
| `apps/api/tests/test_check_model_patterns_v1_3.py` | 新 | 65 | 2 测覆盖新 check |
| `docs/mcp-v4-v1.3-type-mismatch-scan-report.md` | 新 | (本文) | ship report |

## 7. 决策

✅ **防 v0.4d/v1.2 Bug 4 类 Type Mismatch 再发**
- 1 真 mismatch 找到并修 (recommendation.py)
- 防御 check 加 1 条规则 (STRING36_FK_UUID_PATTERN)
- 65/65 累计回归 + 0 违规
- 0.3d (比估时 0.5d 快)

**v1.3 价值**:
- **主动扫**: 不等下次 E2E 暴露, 主动找类似 v0.4d/v1.2 Bug 4 的 schema 不匹配
- **防御检查**: 未来 PR 加新 model 不会再引入同类型 bug
- **更新原 check**: 移除 recommendation.py (其 FK 目标 DB 实际是 uuid, 旧规则误判)

## 8. 累计 MCP v4 Follow-ups 总结

| PR | 估时 | 实际 | 测 | 关键产出 |
|---|---|---|---|---|
| v1.0b.1 | 0.1d | 0.1d | +4 | SENTRY key typo + 兼容 shim |
| v0.7.2 | 0.2d | 0.2d | +4 | skill_cli 鉴权 + 审计 |
| v0.8.1 | 0.3d | 0.3d | 0 | Popen+psutil 真 fd/memory |
| v1.1 | 1.5d | 1.5d | +2 | Phase D E2E + v0.4d UUID bug 修 |
| v1.1.1 | 0.2d | 0.2d | +1 | skills filter 真生效 |
| v0.8.2 | 0.3d | 0.3d | 0 | long-running scenario 推翻 v0.8.1 误判 |
| v1.2 | 1d | 2-3d | +1 | 5 步跨 3 server E2E + 4 hidden bug |
| **v1.3** | **0.5d** | **0.3d** | **+2** | **Type mismatch 扫全 + 防御 check** |
| **合计** | **4.1d** | **4.9-5.9d** | **+14** | **18 ship reports** |

## 9. 后续路径

| 项 | 估时 | 优先级 |
|---|---|---|
| **v1.4**: full pipeline orchestrator E2E (Momus §3 关注) | 1.5d | 低 |
| 健康检查限流 mitigation | 0.2d | 低 (已知 issue) |
| 评估多轮次 R1+R2+R3 测 | 0.3d | 低 |
| 把 v1.1+v1.2 E2E 加到 CI (GitHub Actions workflow) | 0.2d | 中 (目前只 pre-commit 跑检查) |

## 10. 引用

- v1.2 ship report: `docs/mcp-v4-v1.2-eval-interview-e2e-report.md` (类似 hidden bug 模式)
- v0.4d UUID bug fix: commit `145d228` (v1.1 E2E 暴露)
- check_model_patterns.py: `scripts/check_model_patterns.py` (v1.3 加规则 3)
- 修后 recommendation.py: `apps/api/app/models/recommendation.py:54-65`
- E2E 测: `apps/api/tests/test_check_model_patterns_v1_3.py`
- .pre-commit-config.yaml: `check-model-patterns` hook 自动跑
