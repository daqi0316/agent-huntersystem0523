# AI Recruitment System — v3 实施计划

> 基于 2026-05-24 全面扫描 + Momus 审查
> 执行策略: 每次一个 Phase，完成后 `pytest` + `make coverage` + 构建检查

## 当前状态

| 层 | 指标 | 关键缺口 |
|---|---|---|
| 后端 API 端点 (18 文件) | 34/36 端点有真实逻辑 | 2 stub: `/data-aggregate`, `/human-loop/stop`; `/pipeline/generate-report` 也是 stub |
| 后端 Agents (7 个) | 7/7 全实现 | 全部通过 LLM/规则引擎工作 |
| 后端 Services (8 个) | 6/8 有真实逻辑 | **report.py** stub, **interview.py** stub |
| 后端 Models (5 个) | User, Candidate, Application, JobPosition, Interview | **Application 有 model 无 API route** |
| 前端页面 (13 个) | 11/11 dashboard 页对接真实 API | 全部有 API 调用，无纯 mock 页 |
| 测试 | 53 tests / 8 文件 | 10 个模块零测试; 覆盖率仅 50% |
| 工程工具 | Docker Compose ✓, Dockerfiles ✓, CI ✓, Makefile ✓ | 无 Ruff, 无 pre-commit, 无 E2E CI |
| LLM 客户端 | OMLXClient 无 try/except | LLM 不可用时直接抛 500 |

### 已完成的 v2 计划项
- ✅ Makefile（`make dev`, `make test`, `make coverage` 等）
- ✅ `.env.example`（api + web）
- ✅ E2E 基础: `auth.spec.ts`, `candidates.spec.ts`, `jd-generator.spec.ts`, `jobs.spec.ts`, `screening.spec.ts`

---

## Phase 0: 核心 Stub 替换（最高优先级）

### 0.1 ReportService — 真实评估报告生成
- **文件**: `apps/api/app/services/report.py`
- **当前**: 返回 `{"scores": {}, "summary": "Report pending..."}`
- **目标**: 读取 Candidate + Application DB → LLM 生成 5-8 维度评分 + 综合评语 → LLM 不可用时 keyword 降级
- **输出格式**:
  ```python
  {
    "candidate_name": "...", "job_title": "...",
    "score_dimensions": [{"name": "技术能力", "score": 85, "reason": "..."}],
    "overall_score": 82, "summary": "...", "llm_generated": True
  }
  ```
- **改动量**: ~80 行

### 0.2 `/pipeline/generate-report` — 接入 ReportService
- **文件**: `apps/api/app/api/pipeline.py`
- **当前**: `return {"success": True, "message": "报告生成功能将在后续迭代实现"}`
- **改动**: 调用 `ReportService().generate_report()` ~15 行

### 0.3 InterviewService — 真实面试安排
- **文件**: `apps/api/app/services/interview.py`
- **当前**: 返回 `{"status": "pending_approval"}`
- **目标**: 写入 Interview DB 表（model 已存在）+ slot 冲突检测 + confirm 更新 DB
- **改动量**: ~60 行

### 0.4 Application CRUD 端点（Momus 发现）
- **文件**: 新增 `apps/api/app/api/applications.py` + `apps/api/app/services/application.py`
- **当前**: Application model 存在，无 API route
- **目标**: 完整的 CRUD（list / get / create / update / delete）+ 在 router.py 注册
- **改动量**: ~120 行 (新文件)

### 0.5 Settings API 端点（Momus 发现）
- **文件**: 新增 `apps/api/app/api/settings.py` + `apps/api/app/models/setting.py`
- **当前**: Settings 页面纯前端 localStorage
- **目标**: 简单的 key-value 设置读写端点，供前端持久化
- **改动量**: ~80 行 (新文件 + 新 model)

### 0.6 修复 Settings 页面端口
- **文件**: `apps/web/app/(dashboard)/settings/page.tsx`
- **改动**: `localhost:8001` → `localhost:8000`
- **改动量**: 1 行

### ✅ 验证: `pytest` 全部通过 + `lsp_diagnostics` 无错误

---

## Phase 1: 微 Stub 填充（可与 Phase 0 并行）

### 1.1 `/parallel/data-aggregate`
- **文件**: `apps/api/app/api/parallel.py`
- **当前**: `return {"message": "数据聚合将在后续迭代实现"}`
- **目标**: 聚合 evaluation 分数 → 平均分、最高分、维度分布 ~25 行

### 1.2 `/human-loop/stop`
- **文件**: `apps/api/app/api/human_loop.py`
- **当前**: 已返回 `get_pending_count()`
- **目标**: 调用 `agent._pending.clear()` ~5 行

### ✅ 验证: `pytest` 全部通过

---

## Phase 2: 补后端单元测试

### 2.1 新测试文件
| 测试文件 | 测试内容 | 预期 test 数 |
|---|---|---|
| `tests/test_loop.py` | JD 生成 & 改进 (happy/empty/LLM failure) | 4 |
| `tests/test_orchestrator.py` | 任务分解 & DAG 执行 | 4 |
| `tests/test_human_loop.py` | 面试安排 & 审批 (schedule/approve/reject/expire) | 4 |
| `tests/test_retrieval.py` | 向量搜索 & 嵌入 | 3 |
| `tests/test_knowledge.py` | 知识库 CRUD & 搜索 | 4 |
| `tests/test_dashboard.py` | Dashboard 统计 | 3 |
| `tests/test_parallel.py` | 多维度评估 & 数据聚合 | 4 |
| `tests/test_router_route.py` | 意图分类 (rule/LLM/fallback) | 4 |
| `tests/test_report.py` | 评估报告（Phase 0 产物） | 4 |
| `tests/test_interview_service.py` | 面试安排（Phase 0 产物） | 3 |
| `tests/test_applications.py` | 申请 CRUD（Phase 0 产物） | 4 |
| `tests/test_settings.py` | 设置读写（Phase 0 产物） | 3 |

### 2.2 pytest-cov 配置
- **文件**: `apps/api/pyproject.toml`
- **内容**: 添加 pytest 配置，`--cov-fail-under=50`

### ✅ 验证: `make coverage` 达到 50%+ 阈值

---

## Phase 3: 基础设施 & 代码质量

### 3.1 Ruff 配置
- **文件**: `apps/api/pyproject.toml` 添加 `[tool.ruff]` section
- **规则**: line-length=120, select=["E", "F", "I", "N", "W", "UP", "B", "SIM"]

### 3.2 Pre-commit
- **文件**: 根 `.pre-commit-config.yaml`
- **钩子**: ruff check, ruff format, trailing-whitespace, end-of-file-fixer

### 3.3 LLM 客户端容错
- **文件**: `apps/api/app/llm/omlx_client.py`
- **目标**: `chat()` 和 `embed()` 加 try/except → 失败返回降级值而不是抛 500
- **影响**: 所有依赖 LLM 的服务自动获得降级

### 3.4 优雅降级推广
- **参考**: `router_route.py` 的 `use_llm` + fallback 模式
- **文件**: `screening.py` (screen LLM fallback), `knowledge.py` (Qdrant fallback), `report.py` (keyword fallback)

### 3.5 CI 增强
- **文件**: `.github/workflows/ci.yml`
- **改动**: 后端 job 添加 `--cov --cov-fail-under=50`

### ✅ 验证: `ruff check .` 无错误 + CI 模拟通过

---

## Phase 4: 补 E2E 测试

### 4.1 新 E2E Spec (7 files)
| Spec 文件 | 测试场景 |
|---|---|
| `apps/web/e2e/dashboard.spec.ts` | 页面渲染，KPI 卡片展示 |
| `apps/web/e2e/evaluation.spec.ts` | 页面渲染，评估列表 |
| `apps/web/e2e/interview.spec.ts` | 面试安排页面 |
| `apps/web/e2e/knowledge.spec.ts` | 知识库搜索 |
| `apps/web/e2e/talent-profile.spec.ts` | 搜索候选人, 查看详情 |
| `apps/web/e2e/reports.spec.ts` | 页面渲染, 报告列表 |
| `apps/web/e2e/settings.spec.ts` | 加载设置, 修改保存 |

### 4.2 E2E 接入 CI
- CI 添加 E2E job: 启动 services + api + web → playwright test

### ✅ 验证: `npx playwright test` 全部通过

---

## Phase 5: 生产准备（低优先级）

### 5.1 生产配置审查
- JWT secret 强校验: 在 `config.py` 中 `Field(..., validation_alias="JWT_SECRET")`
- CORS 配置审查

### 5.2 错误响应统一
- 所有 4xx/5xx 返回 `{"success": false, "error": "..."}` 格式
- 移除调试 `print()` 语句

### 5.3 Health / Metrics 端点
- 新增 `apps/api/app/api/health.py`: `GET /health` + `GET /metrics`
- prometheus-client 已依赖，只需挂载

### 5.4 README
- 架构图 (ascii)、启动步骤、API 概览

---

## 完整文件变更清单

```
Phase 0:
  apps/api/app/services/report.py          — 替换 stub 为 LLM 生成 (+80 行)
  apps/api/app/api/pipeline.py             — 接入 ReportService (+15 行)
  apps/api/app/services/interview.py       — 替换 stub 为 DB 操作 (+60 行)
  apps/api/app/api/applications.py         — 新增 Application CRUD (+80 行)
  apps/api/app/services/application.py     — 新增 Application service (+60 行)
  apps/api/app/api/settings.py             — 新增 Settings API (+50 行)
  apps/api/app/models/setting.py           — 新增 Setting model (+30 行)
  apps/api/app/api/router.py               — 注册 applications + settings 路由
  apps/web/app/(dashboard)/settings/page.tsx — 修复端口 8001→8000 (1 行)

Phase 1:
  apps/api/app/api/parallel.py             — 实现 data-aggregate (+25 行)
  apps/api/app/api/human_loop.py           — 清理 pending (+5 行)

Phase 2:
  apps/api/tests/test_loop.py              — 新增 (4 tests)
  apps/api/tests/test_orchestrator.py      — 新增 (4 tests)
  apps/api/tests/test_human_loop.py        — 新增 (4 tests)
  apps/api/tests/test_retrieval.py         — 新增 (3 tests)
  apps/api/tests/test_knowledge.py         — 新增 (4 tests)
  apps/api/tests/test_dashboard.py         — 新增 (3 tests)
  apps/api/tests/test_parallel.py          — 新增 (4 tests)
  apps/api/tests/test_router_route.py      — 新增 (4 tests)
  apps/api/tests/test_report.py            — 新增 (4 tests)
  apps/api/tests/test_interview_service.py — 新增 (3 tests)
  apps/api/tests/test_applications.py      — 新增 (4 tests)
  apps/api/tests/test_settings.py          — 新增 (3 tests)
  apps/api/pyproject.toml                  — 添加 pytest-cov 配置

Phase 3:
  .pre-commit-config.yaml                  — 新增
  apps/api/pyproject.toml                  — 添加 Ruff 配置
  .github/workflows/ci.yml                 — 覆盖率 step
  apps/api/app/llm/omlx_client.py          — 加 try/except (+15 行)
  apps/api/app/services/screening.py       — LLM fallback
  apps/api/app/services/knowledge.py       — Qdrant fallback
  apps/api/app/services/report.py          — LLM fallback (和 Phase 0 同一文件)

Phase 4:
  apps/web/e2e/dashboard.spec.ts           — 新增
  apps/web/e2e/evaluation.spec.ts          — 新增
  apps/web/e2e/interview.spec.ts           — 新增
  apps/web/e2e/knowledge.spec.ts           — 新增
  apps/web/e2e/talent-profile.spec.ts      — 新增
  apps/web/e2e/reports.spec.ts             — 新增
  apps/web/e2e/settings.spec.ts            — 新增
  .github/workflows/ci.yml                 — E2E job

Phase 5:
  apps/api/app/api/health.py               — 新增 health/metrics (+30 行)
  apps/api/app/api/router.py               — 注册 health 路由
  apps/api/app/core/config.py              — JWT secret 强校验
  apps/api/app/main.py                     — CORS / 错误格式
  README.md                                — 新增
```
