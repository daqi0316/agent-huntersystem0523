# M1-1 招聘状态机与历史事件 Ship Report

> 日期：2026-06-08  
> 上游基线：`docs/recruitment-agent-m0-baseline.md`  
> 目标：新增招聘深度状态机，不替换旧 `CandidateStatus`，提供受控状态流转入口和历史记录。

---

## 1. 已交付

### 后端模型

- 新增 `apps/api/app/models/candidate_state.py`
  - `RecruitmentCandidateState`
  - `CandidateStateHistory`
  - `TERMINAL_RECRUITMENT_STATES`
- 更新 `apps/api/app/models/candidate.py`
  - 新增 `recruitment_state`
  - 默认值：`new_application`
  - 保留旧 `CandidateStatus`，不破坏现有筛选/面试流程
- 更新 `apps/api/app/models/__init__.py`
  - 导出新模型与枚举

### Service

- 新增 `apps/api/app/services/candidate_state.py`
  - `CandidateStateService.transition`
  - `validate_transition`
  - `get_triggered_actions`
  - 非法转换抛 `CandidateStateTransitionError`

### API

- 更新 `apps/api/app/api/candidates.py`
  - 新增 `POST /api/v1/candidates/{candidate_id}/state`
  - 统一通过 `CandidateStateService` 更新 `recruitment_state`
  - 成功返回 from/to state、triggered_actions、history_id
  - 非法转换返回 400
  - 候选人不存在返回 404

### Schema

- 新增 `apps/api/app/schemas/candidate_state.py`
  - `CandidateStateTransitionRequest`
  - `CandidateStateHistoryRead`
  - `CandidateStateTransitionRead`

### Alembic

- 新增 `apps/api/alembic/versions/m1_1_candidate_recruitment_state.py`
  - 新增 PostgreSQL enum：`recruitment_candidate_state`
  - `candidates.recruitment_state`
  - `candidate_state_history`
  - 相关索引

### Tests

- 新增 `apps/api/tests/test_candidate_state_service.py`
  - 合法 M1 路径通过
  - 非法跳转到 offer 拒绝
  - 终态继续流转拒绝
  - `screening_passed` 触发面试准备动作
  - API 成功流转
  - API 非法流转返回 400

---

## 2. 状态机范围

首版覆盖：

```text
new_application
screening
screening_passed / screening_rejected
first_interview_pending / scheduled / feedback_pending / passed / rejected
second_interview_pending / scheduled / feedback_pending / passed / rejected
offer_negotiation / offer_sent / offer_accepted / offer_rejected
onboarding_pending
hired
probation_tracking / probation_passed / probation_rejected
```

当前只实现受控流转与历史记录；不在 M1-1 做岗位画像、淘汰原因、面试大纲。

---

## 3. 验证结果

### 迁移

```text
uv run alembic upgrade head
通过
```

首次迁移失败原因：PostgreSQL enum 已手动 create，`create_table` 再次自动 create 导致 `DuplicateObjectError`。已修为 `postgresql.ENUM(..., create_type=False)` 复用已创建类型。

### 单元/API 测试

```text
uv run python -m pytest tests/test_candidate_state_service.py
6 passed, 3 warnings
```

组合运行：

```text
uv run python -m pytest tests/test_candidate_state_service.py tests/test_candidates_api.py
```

结果：新增状态机测试 6/6 通过；旧 `test_candidates_api.py` 25 个失败均为 401 鉴权失败，原因是旧测试未覆盖当前 `org_scoped_db` 依赖，与本次状态机新增逻辑无关。

### LSP

```text
basedpyright-langserver 未安装，LSP diagnostics 不可用
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
| 旧候选人 API 测试鉴权过期 | 已发现 | 后续单独修测试 fixture，不阻塞 M1-1 |
| 前端尚未展示 recruitment_state | 未做 | M1-4 做候选人决策链展示时补 |
| 状态流转未写入通用 audit_log | 未做 | M1-1 当前使用专用 history；如需合规审计，后续双写 audit_log |
| triggered_actions 只返回建议 | 符合预期 | M3/M4 再接真实 Agent/通知动作 |

---

## 5. 下一步

进入 M1-2：岗位画像与评分卡。

优先交付：

```text
job_profiles 表
Java_P7 seed
岗位画像读取 API
评分维度/权重/行为锚定结构
```
