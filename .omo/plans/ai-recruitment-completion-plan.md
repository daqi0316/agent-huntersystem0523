# AI Recruitment System — 实施完成计划

## 当前状态摘要

| 层 | 完成度 | 关键缺口 |
|----|--------|---------|
| 后端 API 路由 | 14/14 已注册 | 4 个端点还是 `return {"message"}` stub |
| 后端 Agents | 5/7 有真实逻辑 | orchestrator_agent / router_agent 仅骨架 |
| 后端 Services | 7/9 有逻辑 | interview / report 仅骨架 |
| 前端 11 页面 | 全部有大屏 UI | 8/11 页面使用硬编码 mock 数据，无 API 调用 |
| 前端 Components | 20+ 组件 | 基本完整 |
| 测试 | 0% | 无单元测试、无 E2E 测试 |
| 配置 | 缺失 | 无 .env 文件 |

---

## Phase 1: 填充 4 个关键后端 Stub（最高优先级）

### 1.1 `router_route.py` — 图3 意图分类路由
- **当前**：`@router.post("/classify")` 返回 `{"message": "Intent classification endpoint"}`
- **目标**：接收用户输入 → LLM 识别意图类型（`screening`/`interview`/`jd_generation`/`knowledge_query`/`chat`）→ 返回意图 + 置信度
- **文件**：
  - `apps/api/app/api/router_route.py` — 新增 `ClassifyRequest`/`ClassifyResponse` schema，调用 LLM 分类
  - `apps/api/app/schemas/` — 若有必要可新增 `router.py` schema 文件

### 1.2 `orchestrator.py` — 图5 综合编排
- **当前**：`@router.post("/analyze")` 返回 `{"message": "Orchestrator analysis endpoint"}`
- **目标**：接收复杂任务 → 分解子任务 → 调用对应 agent → 聚合结果
- **文件**：
  - `apps/api/app/api/orchestrator.py` — 新增 schemas + 编排逻辑
  - `apps/api/app/agents/orchestrator_agent.py` — 实现真实编排逻辑

### 1.3 `memory.py` — Agent 记忆持久化
- **当前**：`/read`, `/write` 均返回 message
- **目标**：基于 Redis 的 session 级记忆读写
- **文件**：
  - `apps/api/app/api/memory.py` — 实现读写逻辑

### 1.4 `tools.py` — MCP 工具（邮件/日历）
- **当前**：3 个端点均返回 message
- **目标**：邮件发送（stub 但有真实验证）、日历查询/预约（stub 但有真实数据模拟）
- **文件**：
  - `apps/api/app/api/tools.py` — 实现工具端点

---

## Phase 2: 连接前端到后端

### 2.1 Dashboard — 接入真实统计数据
- **当前**：硬编码 mock 卡片数据
- **目标**：创建 `/api/v1/dashboard/stats` 端点 → 前端调取真实数据
- **文件**：
  - `apps/api/app/api/` — 新增 `dashboard.py`
  - `apps/web/app/(dashboard)/dashboard/page.tsx` — 替换 mock data 为 api 调用

### 2.2 Candidates — 连接到候选人 CRUD API
- **当前**：硬编码候选人列表
- **目标**：调用 `/api/v1/candidates` 端点
- **文件**：
  - `apps/web/app/(dashboard)/candidates/page.tsx` — 添加 api 调用

### 2.3 Screening — 连接到 Pipeline API
- **当前**：已导入 `api` 但可能未调用（需确认）
- **目标**：确保调用 `/api/v1/pipeline/screen-resume` 并处理响应
- **文件**：
  - `apps/web/app/(dashboard)/screening/page.tsx` — 验证并修复 API 集成

### 2.4 Evaluation — 连接报告 API
- **当前**：硬编码评估数据
- **目标**：调用后端报告生成端点
- **文件**：
  - `apps/web/app/(dashboard)/evaluation/page.tsx`

---

## Phase 3: 测试基础设施

### 3.1 后端单元测试
- **目标**：pytest 配置 + 核心 service 单元测试（screening, candidate, job）
- **文件**：
  - `apps/api/pyproject.toml` 或 `pytest.ini` — 测试配置
  - `apps/api/tests/` — 测试目录

### 3.2 E2E 测试
- **目标**：Playwright 配置 + 关键流程 E2E 测试（登录 → 创建职位 → 筛选候选人）
- **文件**：
  - `apps/web/playwright.config.ts` — 已存在？需确认
  - `apps/web/e2e/` — 测试文件

---

## Phase 4: 基础设施

### 4.1 环境变量
- **目标**：前后端 .env.example 文件
- **文件**：
  - `apps/web/.env.example`
  - `apps/api/.env.example`
