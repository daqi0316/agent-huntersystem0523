# M1-3 结构化淘汰原因 Ship Report

> 日期：2026-06-08  
> 上游基线：`docs/recruitment-agent-m0-baseline.md`  
> 前置阶段：`docs/recruitment-agent-m1-2-job-profiles-ship-report.md`  
> 目标：把候选人淘汰从自由文本变成结构化数据，支持后续漏斗分析、寻访策略优化和人才池回流。

---

## 1. 已交付

### 后端模型

- 新增 `apps/api/app/models/rejection.py`
  - `RejectionReason`
  - `CandidateRejectionRecord`
- 更新 `apps/api/app/models/__init__.py`
  - 导出 `RejectionReason`
  - 导出 `CandidateRejectionRecord`

### Schema

- 新增 `apps/api/app/schemas/rejection.py`
  - `RejectionReasonCreate`
  - `RejectionReasonRead`
  - `CandidateRejectRequest`
  - `CandidateRejectionRecordRead`

关键约束：

- 淘汰候选人必须传 `reason_code`
- 必须传 `stage`
- 必须传 `evidence`
- 支持 `application_id`
- 支持 `job_profile_id`
- 支持 `reusable_for_future`
- 支持 `suggested_action`

### Service

- 新增 `apps/api/app/services/rejection.py`
  - `list_reasons`
  - `get_reason_by_code`
  - `create_reason`
  - `list_candidate_records`
  - `reject_candidate`

淘汰时同步动作：

- 创建 `candidate_rejection_records`
- `Candidate.status` 更新为 `failed`
- 如果传入 `application_id`，`Application.status` 更新为 `rejected`
- 按 `stage` 更新 `Candidate.recruitment_state`
  - `screening` → `screening_rejected`
  - `first_interview` → `first_interview_rejected`
  - `second_interview` → `second_interview_rejected`
  - `offer` → `offer_rejected`

### API

- 新增 `apps/api/app/api/rejections.py`
- 更新 `apps/api/app/api/router.py`

新增路由：

```text
GET  /api/v1/rejections/reasons
POST /api/v1/rejections/reasons
GET  /api/v1/rejections/candidates/{candidate_id}/records
POST /api/v1/rejections/candidates/{candidate_id}/reject
```

行为：

- reason code 冲突返回 409
- 候选人不存在返回 404
- 申请不存在返回 404
- 淘汰原因不存在或停用返回 400
- 申请不属于候选人返回 400

### Alembic

- 新增 `apps/api/alembic/versions/m1_3_rejection_reasons.py`
  - 创建 `rejection_reasons`
  - 创建 `candidate_rejection_records`
  - 创建索引
  - seed 10 个标准淘汰原因

### Tests

- 新增 `apps/api/tests/test_rejection_service_api.py`
  - reason 创建持久化
  - reject_candidate 同步 candidate/application 状态
  - unknown reason 拒绝
  - API list reasons
  - API create reason conflict
  - API reject candidate success
  - API reject missing reason 400

---

## 2. 标准淘汰原因 taxonomy

首版 seed 10 类：

```text
TECH_DEPTH_WEAK              技术深度不足
PROJECT_MISMATCH             项目经验不匹配
STABILITY_RISK               稳定性风险
SALARY_TOO_HIGH              薪资期望过高
CULTURE_MISMATCH             文化匹配不足
COMMUNICATION_WEAK           沟通表达弱
HARD_REQUIREMENT_MISS        硬性条件不符
MOTIVATION_UNCLEAR           动机不清晰
MANAGEMENT_EXPERIENCE_WEAK   管理经验不足
PROCESS_DROPOUT              流程流失/无回复
```

---

## 3. 验证结果

### Alembic

```text
uv run alembic upgrade head
通过
```

### 本次测试

```text
uv run python -m pytest tests/test_rejection_service_api.py
7 passed, 3 warnings
```

### M1 相关回归

```text
uv run python -m pytest tests/test_rejection_service_api.py tests/test_candidate_state_service.py tests/test_job_profile_service_api.py
21 passed, 3 warnings
```

### 系统健康检查

```text
bash scripts/health-check.sh
通过：11
失败：0
```

---

## 4. 风险与后续

| 风险 | 状态 | 后续动作 |
|---|---|---|
| 淘汰时直接设置 recruitment_state，未走 CandidateStateService 合法转换 | 已接受 | 当前目标是记录结构化淘汰事实；后续 M1-4 可统一决策链入口 |
| 前端尚未展示淘汰原因 | 未做 | M1-4 候选人详情决策链展示时接入 |
| 未写通用 audit_log | 未做 | 如合规要求增强，可在 reject_candidate 中双写 audit_log |
| taxonomy 是全局标准 | 已接受 | 后续客户自定义原因可增加 org-scoped reason |

---

## 5. 下一步

进入 M1-4：候选人详情决策链展示。

优先交付：

```text
候选人详情聚合 recruitment_state/history
岗位画像摘要
结构化淘汰记录
面试/反馈/申请状态
缺失字段显示“未采集”
```
