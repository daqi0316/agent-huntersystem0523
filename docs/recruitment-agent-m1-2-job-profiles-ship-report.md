# M1-2 岗位画像与评分卡 Ship Report

> 日期：2026-06-08  
> 上游基线：`docs/recruitment-agent-m0-baseline.md`  
> 前置阶段：`docs/recruitment-agent-m1-1-state-machine-ship-report.md`  
> 目标：新增独立岗位画像库，首版 seed `Java_P7`，为 M2 风险评分与 M3 面试大纲提供结构化标准。

---

## 1. 决策

Oracle 审查任务因余额不足失败，未产出结论。M1-2 采用 M0/Momus 已冻结方案：

- `job_profiles` 独立表，不替换 `job_positions`
- 第一版只 seed `Java_P7`
- 画像字段以 JSON 结构承载评分维度、行为锚定、薪酬带宽和面试重点
- 不做多岗位扩展、不做自动画像优化、不做薪酬谈判 Agent

---

## 2. 已交付

### 后端模型

- 新增 `apps/api/app/models/job_profile.py`
  - `JobProfile`
  - `code` 唯一，例如 `Java_P7`
  - `hard_requirements`
  - `soft_requirements`
  - `evaluation_dimensions`
  - `salary_band`
  - `interview_focus`
  - `is_active`
- 更新 `apps/api/app/models/__init__.py`
  - 导出 `JobProfile`

### Schema

- 新增 `apps/api/app/schemas/job_profile.py`
  - `ScoreAnchor`
  - `EvaluationDimension`
  - `SalaryBand`
  - `JobProfileCreate`
  - `JobProfileUpdate`
  - `JobProfileRead`

关键校验：

- `evaluation_dimensions.weight` 总和必须等于 `1.0`
- `score` 只能是 `1-5`
- `salary_band.base_min <= base_max`
- `salary_band.total_min <= total_max`

### Service

- 新增 `apps/api/app/services/job_profile.py`
  - `list`
  - `get_by_id`
  - `get_by_code`
  - `create`
  - `update`

### API

- 新增 `apps/api/app/api/job_profiles.py`
- 更新 `apps/api/app/api/router.py`

新增路由：

```text
GET  /api/v1/job-profiles
GET  /api/v1/job-profiles/{profile_id}
GET  /api/v1/job-profiles/code/{code}
POST /api/v1/job-profiles
PUT  /api/v1/job-profiles/{profile_id}
```

行为：

- 创建时 `code` 冲突返回 409
- 不存在返回 404
- 列表支持 `search`、`level`、`is_active`

### Alembic

- 新增 `apps/api/alembic/versions/m1_2_job_profiles.py`
  - 创建 `job_profiles`
  - 创建索引：`code/title/level/is_active`
  - seed `Java_P7`

### Tests

- 新增 `apps/api/tests/test_job_profile_service_api.py`
  - 权重总和校验
  - 薪酬范围校验
  - service get/create
  - API list
  - API code not found
  - API create conflict
  - API update not found

---

## 3. Java_P7 seed 内容

首版画像包含：

```text
硬性要求：本科、5年 Java、高并发、Spring Cloud/Dubbo
软性要求：模块设计、跨团队协作、技术热情
评分维度：技术深度 30%、项目经验 25%、学习能力 15%、文化匹配 15%、潜力 15%
薪酬带宽：base 40k-50k，总包 60万-80万
面试重点：主导程度、高并发细节、云原生短板、项目包装识别
```

---

## 4. 验证结果

### Alembic

```text
uv run alembic upgrade head
通过
```

首次迁移失败原因：`op.execute` 传参方式错误，Alembic 不接受独立 params。已修为 `op.get_bind().execute(statement, params)`。

### 本次相关测试

```text
uv run python -m pytest tests/test_job_profile_service_api.py
8 passed, 3 warnings
```

```text
uv run python -m pytest tests/test_job_profile_service_api.py tests/test_job_service.py
19 passed, 3 warnings
```

组合运行包含旧 `tests/test_jobs.py` 时，旧测试 9 个 401 失败，原因是旧 API 测试 fixture 未覆盖当前 `org_scoped_db` 鉴权依赖；与本次 `job_profiles` 新增逻辑无关。

### 系统健康检查

```text
bash scripts/health-check.sh
通过：11
失败：0
```

---

## 5. 风险与后续

| 风险 | 状态 | 后续动作 |
|---|---|---|
| JSON 字段灵活但 DB 层无法强约束内部结构 | 已接受 | Pydantic schema/API 层强校验；M2 使用 schema 读取 |
| `job_profiles` 暂无 org_id | 已接受 | 首版作为全局模板库；如后续客户自定义画像，再加 org-scoped profile |
| 前端尚未展示岗位画像 | 未做 | M1-4 或 M2 页面增强时接入 |
| 旧 `test_jobs.py` 鉴权 fixture 过期 | 已记录 | 单独技术债处理，不阻塞 M1-2 |

---

## 6. 下一步

进入 M1-3：结构化淘汰原因。

优先交付：

```text
rejection reason taxonomy
候选人/投递淘汰记录
淘汰时必填 reason_category / primary_reason / evidence / stage
候选人详情展示淘汰原因
```
