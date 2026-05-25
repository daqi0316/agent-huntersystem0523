# AI Recruitment System — v2 实施计划

> **模型**: deepseek-v4-flash-free (context 有限 → 每个 Phase 独立执行, 避免一次性加载)

## 当前状态 (2026-05-24 全面扫描)

| 层 | 完成度 | 关键缺口 |
|---|---|---|
| 后端 API 路由 (18 文件) | ~34/36 端点真实逻辑 | 2 个 stub: `/data-aggregate`, `/human-loop/stop`; **`/pipeline/generate-report` 也是 stub** |
| 后端 Agents (7 个) | 7/7 全真实逻辑 | 全部通过 LLM/规则引擎工作 |
| 后端 Services (8 个) | 6/8 真实逻辑 | **report.py stub**, **interview.py stub** |
| 后端 LLM Client | OMLXClient 无任何 try/except | LLM 不可用时直接抛 500 |
| 前端页面 (13 个, 11 dashboard) | 11/11 对接真实 API | 全部有 API 调用 |
| 测试 | 53 个 test func, 8 文件 | 8 模块零测试; 无 E2E 测 dashboard/evaluation 等 |
| CI/Docker | Docker Compose ✓, CI workflow ✓ | 无覆盖率追踪, E2E 未接入 CI, 无 ruff/pre-commit |
| 工程工具 | .env.example ✓, Alembic 初始迁移 ✓ | 无 Makefile, 无 pre-commit, 无 ruff 配置 |

---

## 执行策略

- **每次只做一个 Phase**, 完成后 run tests verify, 再开始下一个
- 并行: 同一 Phase 内的独立任务可并行
- 验证: 每个任务完成后 `lsp_diagnostics` + `pytest` (现有 53 个不能红)

---

## Phase 0: 报告端点 + Generate Report 端点接入（最高优先级）

### 0.1 修复 `/pipeline/generate-report`
- **文件**: `apps/api/app/api/pipeline.py`
- **当前**: `return {"success": True, "message": "报告生成功能将在后续迭代实现"}`
- **目标**: 调用 `ReportService().generate_report()` 并返回结构化结果
- **改动量**: ~15 行

### 0.2 ReportService — 真实评估报告生成
- **文件**: `apps/api/app/services/report.py`
- **当前**: 返回硬编码 `{"scores": {}, "summary": "Report pending..."}`
- **目标**: 
  - 读取 Candidate + Application DB 数据
  - 用 LLM 生成 5-8 维度评分 (技术、沟通、经验匹配等) + 综合评语
  - LLM 不可用时返回基于 keyword 的降级评分
- **输出格式**:
  ```python
  {
    "candidate_name": "...",
    "job_title": "...",
    "score_dimensions": [
      {"name": "技术能力", "score": 85, "reason": "..."},
      ...
    ],
    "overall_score": 82,
    "summary": "...",
    "llm_generated": True
  }
  ```
- **改动量**: ~80 行
- **测试**: `tests/test_report.py` (4 tests)

### 0.3 InterviewService — 真实面试安排
- **文件**: `apps/api/app/services/interview.py`
- **当前**: 返回 `{"status": "pending_approval"}` 占位
- **目标**: 
  - 写入 Interview DB 表 (model 已存在)
  - 基本的 slot 冲突检测 (同一 candidate 同一天不能有 2 个面试)
  - confirm() 更新 DB 状态
- **改动量**: ~60 行
- **测试**: `tests/test_interview_service.py` (3 tests)

---

## Phase 1: 填充微小 Stub（高优先级, 可直接和 Phase 0 并行）

### 1.1 Parallel /data-aggregate
- **文件**: `apps/api/app/api/parallel.py`
- **当前**: `return {"message": "数据聚合将在后续迭代实现"}`
- **目标**: 聚合多个 candidate 的 evaluation 分数 -> 平均分、最高分、维度分布
- **改动量**: ~25 行

### 1.2 HumanLoop /stop — 清理 pending 提案
- **文件**: `apps/api/app/api/human_loop.py`
- **当前**: 已返回 `get_pending_count()`
- **目标**: 调用 `agent._pending.clear()`
- **改动量**: ~5 行

---

## Phase 2: 补后端单元测试（高优先级）

### 2.1 新测试文件 (每文件 3-6 tests)
| 测试文件 | 测试模块 | 测试内容 |
|---------|---------|---------|
| `tests/test_loop.py` | Gen-Eval JD 生成 & 改进 | happy path, empty input, LLM failure |
| `tests/test_orchestrator.py` | 任务分解 & DAG 执行 | decompose, execute, aggregate |
| `tests/test_human_loop.py` | 面试安排 & 审批 | schedule, approve, reject, expire |
| `tests/test_retrieval.py` | 向量搜索 & 嵌入 | search, embed, empty query |
| `tests/test_knowledge.py` | 知识库 CRUD & 搜索 | ingest, query, chunk text |
| `tests/test_dashboard.py` | Dashboard 统计 | stats format, empty DB |
| `tests/test_parallel.py` | 多维度评估 & 数据聚合 | multi-evaluate, data-aggregate |
| `tests/test_router_route.py` | 意图分类 | rule matching, LLM boost, fallback |
| `tests/test_report.py` | 评估报告 (Phase 0 产物) | generate, get, LLM failure fallback |
| `tests/test_interview_service.py` | 面试安排 (Phase 0 产物) | schedule, confirm, conflict |

### 2.2 配置覆盖率工具
- **文件**: `apps/api/pyproject.toml`
- **内容**: 添加 `[tool.pytest.ini_options]` 含 `testpaths`, `addopts = "--cov=app --cov-report=term-missing --cov-fail-under=50"`
- **目标**: 起步 50% 阈值 (已有 0% → 需要 50% 合理渐进)

---

## Phase 3: 基础设施（中优先级）

### 3.1 Makefile
- **文件**: 根 `Makefile`
- **目标**: 
  ```makefile
  dev-api       # docker compose up api + deps
  dev-web       # cd apps/web && pnpm dev
  test          # cd apps/api && pytest
  test-cov      # pytest with coverage
  lint          # ruff check
  format        # ruff format
  docker-up     # docker compose up -d
  docker-down   # docker compose down
  ```

### 3.2 Ruff 配置 + Pre-commit
- **文件**: `apps/api/pyproject.toml` (Ruff section), 根 `.pre-commit-config.yaml`
- **Ruff**: line-length=120, select=["E", "F", "I", "N", "W", "UP", "B", "SIM"]
- **Pre-commit**: ruff check, ruff format, trailing-whitespace, end-of-file-fixer

### 3.3 CI 增强
- **文件**: `.github/workflows/ci.yml`
- **改动**:
  - 后端: 添加 `--cov --cov-fail-under=50`
  - 添加前端 lint + type-check step
  - 添加 E2E 测试 job (需启动 services + api + web)

### 3.4 LLM 客户端容错
- **文件**: `apps/api/app/llm/omlx_client.py`
- **当前**: 无 try/except, LLM 挂 = 500
- **目标**: 
  - `chat()` 用 try/except 包裹, 失败返回 `"[LLM unavailable]"` 而不是抛异常
  - `embed()` 同, 失败返回空列表
- **改动量**: ~15 行
- **影响**: 所有依赖 LLM 的服务自动获得降级 (不会 500)

### 3.5 优雅降级模式推广
- **参考**: `router_route.py` 的 `use_llm` + try/except + fallback 模式
- **文件**:
  - `apps/api/app/services/screening.py` — screen/multi-evaluate LLM 调用加 fallback
  - `apps/api/app/services/knowledge.py` — Qdrant 连接失败时 fallback 到关键词搜索
  - `apps/api/app/services/report.py` — LLM 失败时用 keyword-based 评分
- **改动量**: 每个文件 ~15 行

---

## Phase 4: 补 E2E 测试（中优先级）

### 4.1 新 E2E spec 文件
| Spec 文件 | 测试场景 |
|-----------|---------|
| `dashboard.spec.ts` | 页面渲染, 检查 KPI 卡片展示 |
| `evaluation.spec.ts` | 页面渲染, 检查评估列表 |
| `interview.spec.ts` | 页面渲染, 查看面试安排 |
| `knowledge.spec.ts` | 页面渲染, 检查知识库搜索 |
| `talent-profile.spec.ts` | 搜索候选人, 查看详情 |
| `reports.spec.ts` | 页面渲染, 查看报告列表 |
| `settings.spec.ts` | 加载设置, 修改并保存 |

### 4.2 Playwright config 审查
- **文件**: `apps/web/playwright.config.ts`
- **检查**: baseURL 支持 env 覆盖, CI 兼容性

### 4.3 E2E 接入 CI
- 在 CI workflow 中添加 E2E job
- 使用 `docker compose` 启动所有依赖 + api + web
- 使用 `npx playwright install --with-deps`

---

## Phase 5: 生产准备（低优先级）

### 5.1 生产配置审查
- JWT secret: `apps/api/app/core/config.py` 中添加 `jwt_secret: str = Field(..., validation_alias="JWT_SECRET")` 强制 env 注入
- CORS: 检查 `apps/api/app/main.py` 中的 `CORSMiddleware` 配置
- 日志: 配置 `logging.level` 从环境变量读取

### 5.2 项目文档
- `README.md`: 架构图 (ascii)、启动步骤、API 概览、环境变量说明

### 5.3 清理
- `grep -rn 'print(' apps/api/app/` 排查并移除调试语句
- 统一错误响应格式: 所有 4xx/5xx 返回 `{"success": false, "error": "..."}`

---

## 快速参考: 所有文件变更清单

```
Phase 0:
  apps/api/app/api/pipeline.py          — 接入 ReportService (+15 行)
  apps/api/app/services/report.py       — 替换 stub 为 LLM 生成 (+80 行)
  apps/api/app/services/interview.py    — 替换 stub 为 DB 操作 (+60 行)
  apps/api/tests/test_report.py         — 新增 (4 tests)
  apps/api/tests/test_interview_service.py — 新增 (3 tests)

Phase 1:
  apps/api/app/api/parallel.py          — 实现 data-aggregate (+25 行)
  apps/api/app/api/human_loop.py        — 清理 pending (+5 行)

Phase 2:
  apps/api/tests/test_loop.py           — 新增 (4 tests)
  apps/api/tests/test_orchestrator.py   — 新增 (4 tests)
  apps/api/tests/test_human_loop.py     — 新增 (4 tests)
  apps/api/tests/test_retrieval.py      — 新增 (3 tests)
  apps/api/tests/test_knowledge.py      — 新增 (4 tests)
  apps/api/tests/test_dashboard.py      — 新增 (3 tests)
  apps/api/tests/test_parallel.py       — 新增 (4 tests)
  apps/api/tests/test_router_route.py   — 新增 (4 tests)
  apps/api/pyproject.toml               — 添加 pytest-cov 配置

Phase 3:
  Makefile                               — 新增
  .pre-commit-config.yaml                — 新增
  apps/api/pyproject.toml                — 添加 Ruff 配置
  .github/workflows/ci.yml               — 覆盖率 + E2E job
  apps/api/app/llm/omlx_client.py        — 加 try/except (+15 行)
  apps/api/app/services/screening.py     — LLM fallback
  apps/api/app/services/knowledge.py     — Qdrant fallback
  apps/api/app/services/report.py        — LLM fallback (和 Phase 0 同一文件)

Phase 4:
  apps/web/e2e/dashboard.spec.ts         — 新增
  apps/web/e2e/evaluation.spec.ts        — 新增
  apps/web/e2e/interview.spec.ts         — 新增
  apps/web/e2e/knowledge.spec.ts         — 新增
  apps/web/e2e/talent-profile.spec.ts    — 新增
  apps/web/e2e/reports.spec.ts           — 新增
  apps/web/e2e/settings.spec.ts          — 新增
  .github/workflows/ci.yml               — E2E job

Phase 5:
  apps/api/app/core/config.py            — JWT secret 强校验
  apps/api/app/main.py                   — CORS / 日志
  README.md                              — 新增
```
