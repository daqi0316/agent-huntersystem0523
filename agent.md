# AI Recruitment System · Agent Implementation Plan

> 基于 `AI_Recruitment_System_PRD.md` v1.0  
> 作者：qixia · Sisyphus  
> 日期：2026-05-23

---

## 一、项目概述

### 1.1 目标
搭建一套可售卖的 AI 招聘 SaaS 系统，包含 7 种 AI Agent 架构模式、11 个前端页面、企业级后端基础设施。

### 1.2 核心技术栈

| 层 | 技术 | 版本 |
|---|------|------|
| Monorepo | Turborepo + pnpm | latest |
| 前端 | Next.js + TypeScript + Tailwind + shadcn/ui | 14 / 5.4+ / 3.4+ |
| API协议 | tRPC + SuperJSON + Zod | 11+ / 3.23+ |
| 状态管理 | Zustand (客户端) + React Query (服务端) | 4+ / 5+ |
| 后端 | FastAPI + Uvicorn + Gunicorn | 0.111 / 0.30 |
| 数据库 | PostgreSQL 16 (主从 + 读写分离) | 16 |
| 向量库 | Qdrant + bge-m3 嵌入 | latest |
| 缓存 | Redis 7 | 7 |
| 消息队列 | RabbitMQ | latest |
| AI推理 | vLLM + Qwen3.6 (本地) / omlx (开发) | latest |
| 对象存储 | MinIO (S3 兼容) | latest |
| 可观测性 | Prometheus + Grafana + Loki | latest |
| 部署 | Vercel Pro (前端) + Docker (后端) | |

---

## 二、架构设计

### 2.1 整体架构（三层）

```
┌─────────────────────────────────────────────┐
│        前端层 (apps/web)                     │
│  Next.js 14 App Router · 11 页面            │
│  tRPC Client · React Query · Zustand        │
│  shadcn/ui · Tailwind · Recharts · SSE       │
├─────────────────────────────────────────────┤
│        编排层 (apps/api)                     │
│  GlobalRouter → 7 种 Agent Pattern          │
│  图1 单Agent · 图2 流水线 · 图3 Router      │
│  图4 Aggregator · 图5 Orchestrator          │
│  图6 Gen-Eval · 图7 Human-in-Loop           │
├─────────────────────────────────────────────┤
│        基础设施层 (Docker Compose)            │
│  PostgreSQL 16 · Qdrant · Redis 7           │
│  RabbitMQ · MinIO · vLLM · Prometheus+Grafana│
└─────────────────────────────────────────────┘
```

### 2.2 7 种 Agent 架构分配

| 页面 | 名称 | 主架构 | 辅助架构 | 优先级 |
|------|------|--------|---------|--------|
| 4 | **AI初筛** | 图2 流水线 | 图4 Aggregator | **P0** |
| 8 | **JD生成器** | 图6 Gen-Eval | - | P1 |
| 5 | **面试安排** | 图7 Human-in-Loop | - | P1 |
| 3 | **候选人库** | 图1 单Agent+RAG | - | P1 |
| 2 | **职位管理** | 图3 Router | 图6/图7 | P1 |
| 6 | **评估报告** | 图2 流水线 | 图6 Gen-Eval | P1 |
| 1 | **数据看板** | 图1 单Agent | - | P2 |
| 7 | **人才画像** | 图5 Orchestrator | 图4 Aggregator | P2 |
| 9 | **数据报表** | 图4 Aggregator | 图5 Orchestrator | P2 |
| 10 | **系统设置** | 无AI | - | P1 |
| 11 | **知识库** | 图1 单Agent+RAG | - | P1 |

---

## 三、项目结构

```
ai-recruitment/                         # Monorepo 根目录
├── agent.md                            # ← 本文档（实施指南）
├── AI_Recruitment_System_PRD.md        # PRD 原始文档
├── package.json                        # 根 workspace 配置
├── pnpm-workspace.yaml                 # pnpm 工作区定义
├── turbo.json                          # Turborepo 流水线
├── .gitignore
├── apps/api/.env.example  # API 环境变量
│
├── apps/
│   ├── web/                            # 前端 - Next.js 14
│   │   ├── package.json
│   │   ├── next.config.js
│   │   ├── tsconfig.json
│   │   ├── tailwind.config.ts
│   │   ├── postcss.config.js
│   │   ├── app/                        # App Router
│   │   │   ├── layout.tsx              # 根布局（ThemeProvider）
│   │   │   ├── page.tsx                # 首页重定向到 /dashboard
│   │   │   ├── (auth)/                 # 认证路由组
│   │   │   │   ├── login/page.tsx
│   │   │   │   └── layout.tsx
│   │   │   └── (dashboard)/            # 工作台路由组
│   │   │       ├── layout.tsx          # Sidebar + Header 布局
│   │   │       ├── dashboard/          # 页面1: 数据看板
│   │   │       ├── jobs/               # 页面2: 职位管理
│   │   │       ├── candidates/         # 页面3: 候选人库
│   │   │       ├── screening/          # 页面4: AI初筛 (P0)
│   │   │       ├── interview/          # 页面5: 面试安排
│   │   │       ├── evaluation/         # 页面6: 评估报告
│   │   │       ├── talent-profile/     # 页面7: 人才画像
│   │   │       ├── jd-generator/       # 页面8: JD生成器
│   │   │       ├── reports/            # 页面9: 数据报表
│   │   │       ├── settings/           # 页面10: 系统设置
│   │   │       └── knowledge/          # 页面11: 知识库
│   │   ├── components/
│   │   │   ├── ui/                     # shadcn/ui 基础组件
│   │   │   ├── common/                 # 业务通用组件
│   │   │   │   ├── sidebar.tsx
│   │   │   │   ├── header.tsx
│   │   │   │   ├── data-table.tsx
│   │   │   │   └── empty-state.tsx
│   │   │   └── features/              # 功能模块组件
│   │   │       ├── screening/          # AI初筛相关
│   │   │       │   ├── candidate-card.tsx
│   │   │       │   ├── match-score-badge.tsx
│   │   │       │   └── pipeline-status.tsx
│   │   │       ├── interview/          # 面试安排相关
│   │   │       │   └── calendar-view.tsx
│   │   │       └── report/             # 报表相关
│   │   │           ├── score-radar.tsx
│   │   │           └── report-card.tsx
│   │   ├── hooks/
│   │   │   ├── use-candidates.ts       # React Query hooks
│   │   │   ├── use-pipeline-progress.ts # SSE 流水线进度
│   │   │   └── use-debounce.ts
│   │   ├── lib/
│   │   │   ├── trpc.ts                # tRPC 客户端
│   │   │   ├── utils.ts               # cn() 工具函数
│   │   │   └── constants.ts
│   │   ├── stores/
│   │   │   └── ui-store.ts            # Zustand UI 状态
│   │   ├── types/
│   │   │   └── index.ts               # 前端类型
│   │   └── styles/
│   │       └── globals.css            # Design Tokens + Tailwind
│   │
│   └── api/                           # 后端 - FastAPI
│       ├── package.json               # (only for workspace ref)
│       ├── pyproject.toml             # Python 项目配置
│       ├── requirements.txt
│       ├── alembic.ini
│       ├── alembic/
│       │   ├── env.py
│       │   └── versions/
│       ├── app/
│       │   ├── __init__.py
│       │   ├── main.py                # FastAPI 入口
│       │   ├── core/
│       │   │   ├── __init__.py
│       │   │   ├── config.py          # 全局配置
│       │   │   ├── database.py        # PostgreSQL 读写分离
│       │   │   ├── redis.py           # Redis 服务
│       │   │   ├── qdrant.py          # Qdrant 向量库
│       │   │   ├── security.py        # JWT 认证
│       │   │   └── dependencies.py    # FastAPI 依赖注入
│       │   ├── models/                # SQLAlchemy ORM
│       │   │   ├── __init__.py
│       │   │   ├── candidate.py
│       │   │   ├── job_position.py
│       │   │   ├── application.py
│       │   │   └── interview.py
│       │   ├── schemas/               # Pydantic v2
│       │   │   ├── __init__.py
│       │   │   ├── candidate.py
│       │   │   ├── job.py
│       │   │   ├── screening.py
│       │   │   └── common.py
│       │   ├── api/                   # API 路由
│       │   │   ├── __init__.py
│       │   │   ├── router.py          # 全局 Router
│       │   │   ├── agent.py           # 图1: 单Agent
│       │   │   ├── pipeline.py        # 图2: 流水线
│       │   │   ├── router_route.py    # 图3: Router
│       │   │   ├── parallel.py        # 图4: Aggregator
│       │   │   ├── orchestrator.py    # 图5: Orchestrator
│       │   │   ├── loop.py            # 图6: Gen-Eval
│       │   │   ├── human_loop.py      # 图7: Human-in-Loop
│       │   │   ├── tools.py           # MCP 工具
│       │   │   ├── retrieval.py       # 向量检索
│       │   │   └── memory.py          # 记忆管理
│       │   ├── agents/                # 7 种 Agent 实现
│       │   │   ├── __init__.py
│       │   │   ├── base.py            # BaseAgent 抽象
│       │   │   ├── single_agent.py
│       │   │   ├── pipeline.py
│       │   │   ├── router_agent.py
│       │   │   ├── aggregator.py
│       │   │   ├── orchestrator_agent.py
│       │   │   ├── gen_eval_loop.py
│       │   │   └── human_loop.py
│       │   ├── services/              # 业务逻辑
│       │   │   ├── __init__.py
│       │   │   ├── screening.py       # AI初筛
│       │   │   ├── jd_generator.py
│       │   │   ├── interview.py
│       │   │   └── report.py
│       │   └── llm/                   # LLM 接口
│       │       ├── __init__.py
│       │       ├── base.py            # LLM 抽象接口
│       │       ├── vllm_client.py     # vLLM 调用
│       │       └── omlx_client.py     # omlx 本地
│       └── tests/
│           ├── __init__.py
│           ├── test_pipeline.py
│           └── test_agents.py
│
├── packages/
│   ├── types/                         # 共享 TypeScript 类型
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   │       ├── index.ts
│   │       ├── candidate.ts
│   │       ├── job.ts
│   │       └── api.ts
│   ├── config/                        # 共享配置
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   ├── eslint-preset.js
│   │   └── typescript-config.json
│   └── utils/                         # 共享工具
│       ├── package.json
│       ├── tsconfig.json
│       └── src/
│           ├── index.ts
│           ├── format.ts
│           └── validation.ts
│
├── docker-compose.yml                 # 基础设施
├── docker-compose.dev.yml             # 开发环境
│
└── scripts/
    ├── dev.sh                         # 本地开发启动
    └── seed.py                        # 数据初始化
```

---

## 四、三阶段实施路线

### 第一阶段：基础设施 + MVP（2-3 周）
> 目标：可演示的 AI 功能

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 1.1 | Monorepo 脚手架 | Turborepo + pnpm 工作区 | - |
| 1.2 | 后端 FastAPI 基础 | main.py, 配置, DB 连接 | 1.1 |
| 1.3 | 前端 Next.js 基础 | App Router, 布局, 主题 | 1.1 |
| 1.4 | 4 个核心数据模型 | Candidate, JobPosition, Application, Interview | 1.2 |
| 1.5 | 页面8: JD生成器（图1 单Agent） | 前端 + 后端 API | 1.3 |
| 1.6 | 页面11: 知识库问答（图1+RAG） | 前端 + 向量检索 | 1.5 |
| 1.7 | 接入 omlx + Qwen3.6 | LLM 接口封装 | 1.2 |
| 1.8 | Docker Compose 基础设施 | PG, Qdrant, Redis, MinIO | - |

### 第二阶段：流水线 + 核心功能（3-4 周）
> 目标：核心 AI 初筛跑通

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 2.1 | 页面4: AI初筛（图2 流水线） | Pipeline Engine + Gate 质检 | 1.7, 1.8 |
| 2.2 | 页面4 Step3: Aggregator 多维度评估 | 图4 并行 LLM + 合并 | 2.1 |
| 2.3 | 向量数据库 + bge-m3 嵌入 | Qdrant 服务封装 | 1.8 |
| 2.4 | 页面6: 评估报告（图2+图6） | 报告生成 API + 前端 | 2.2 |
| 2.5 | 页面3: 候选人库 | CRUD + 搜索 + 标签 | 1.4 |
| 2.6 | 页面2: 职位管理（图3 Router） | Router 意图分发 | 2.5 |
| 2.7 | 前端 tRPC 端到端类型安全 | tRPC Router + React Query hooks | 1.3 |

### 第三阶段：高级功能 + 商业化（4-6 周）
> 目标：完整 SaaS 产品

| # | 任务 | 产出 | 依赖 |
|---|------|------|------|
| 3.1 | 页面5: 面试安排（图7 Human-in-Loop） | 日历 + 邮件 + Stop 按钮 | 2.7 |
| 3.2 | MCP 工具接入 | 邮件/日历 MCP Server | 3.1 |
| 3.3 | 页面7: 人才画像（图5 Orchestrator） | 动态拆解 + 合成 | 2.7 |
| 3.4 | 页面9: 数据报表（图4 Aggregator） | 多数据源合并 | 2.7 |
| 3.5 | 页面1: 数据看板 | 招聘漏斗 + 转化率 | 3.4 |
| 3.6 | 页面10: 系统设置 | 模型配置 + API 密钥 | 2.7 |
| 3.7 | 可观测性 | Prometheus + Grafana + Loki | - |
| 3.8 | 部署 | Vercel Pro + Docker 生产 | 全部 |

---

## 五、质量要求

### 5.1 代码质量
- 后端: Pydantic v2 类型验证，SQLAlchemy 异步，Alembic 迁移
- 前端: TypeScript strict，Zod 运行时验证，ESLint + Prettier
- 端到端类型安全: tRPC 自动推导

### 5.2 测试要求
| 类型 | 工具 | 覆盖 |
|------|------|------|
| 前端单元测试 | Vitest + @testing-library/react | 80%+ |
| 后端测试 | pytest | 80%+ |
| E2E | Playwright | 核心流程 |

### 5.3 安全要求
- JWT 认证（python-jose + passlib）
- 所有 API 需认证（除 login/register）
- CORS 限制，Rate Limiting（Redis）
- 无硬编码密钥（环境变量）
- SQL 注入防护（SQLAlchemy 参数化）

### 5.4 Git 规范
```
格式: <type>: <description>
类型: feat, fix, refactor, docs, test, chore, perf
示例: feat: add AI screening pipeline engine
      fix: correct gate check null pointer
      refactor: extract base agent class
```

---

## 六、开发流程

### 6.1 日常工作流
1. `pnpm dev` — 启动全部服务 (Next.js + FastAPI + Docker 基础设施)
2. 按 `agent.md` 阶段顺序开发
3. 每个功能先写 TDD 测试 (RED → GREEN → REFACTOR)
4. 开发完成后 `/review-work` 自动审查
5. 提交 PR 前运行完整测试套件

### 6.2 启动命令
```bash
# 安装依赖
pnpm install

# 启动基础设施 (PostgreSQL, Qdrant, Redis)
docker compose -f docker-compose.dev.yml up -d

# 启动后端 (FastAPI)
pnpm --filter @ai-recruitment/api dev

# 启动前端 (Next.js)
pnpm --filter @ai-recruitment/web dev

# 或一键全部启动
pnpm dev
```

---

## 七、关键设计决策

### 7.1 为什么 tRPC 而非 REST？
- 端到端类型安全：从数据库 Schema → Zod → tRPC → React Query → 组件
- 零样板代码：不需要手动维护 OpenAPI 定义和客户端生成
- 与 Next.js 无缝集成，适合全栈团队

### 7.2 为什么 FastAPI 而非 Django/Node？
- Python 是 AI/ML 唯一生态语言
- FastAPI 异步原生，性能接近 Node.js
- Pydantic v2 自动生成 OpenAPI + 类型校验
- AutoGPT/AI 工具链全部 Python 生态

### 7.3 为什么 Qdrant 而非 Pinecone/Milvus？
- Rust 编写，性能极高，可本地 Docker 部署
- 数据不出域（满足数据隐私要求）
- 支持复杂 Filter（招聘筛选需求），GRPC 协议
- 无需 SaaS 费用

### 7.4 7 图混合架构设计原则
- **简单任务 → 图1 单Agent**：JD 生成、知识库问答
- **标准化流程 → 图2 流水线**：AI 初筛简历（带 Gate 质检）
- **多类型任务 → 图3 Router**：职位管理（创建/发布）
- **多角度分析 → 图4 Aggregator**：候选人评估、报表
- **复杂综合分析 → 图5 Orchestrator**：人才画像、招聘分析报告
- **高质量要求 → 图6 Gen-Eval**：高质量 JD、面试题生成
- **涉及外部系统 → 图7 Human-in-Loop**：面试安排、邮件发送

---

## 八、API 路由总览

```
POST /api/v1/router/classify         # 全局意图识别

GET  /api/v1/agent/chat              # 图1: 对话
POST /api/v1/agent/generate-jd       # 图1: JD生成（简化版）
POST /api/v1/agent/knowledge-query   # 图1: 知识库问答

POST /api/v1/pipeline/screen-resume  # 图2: AI初筛流水线
GET  /api/v1/pipeline/{id}/progress  # SSE: 流水线进度
POST /api/v1/pipeline/generate-report # 图2: 评估报告

POST /api/v1/parallel/multi-evaluate # 图4: 多维度评估
POST /api/v1/parallel/data-aggregate # 图4: 数据聚合

POST /api/v1/orchestrator/analyze    # 图5: 综合分析

POST /api/v1/loop/iterative-generate # 图6: 循环生成

POST /api/v1/human-loop/schedule     # 图7: 面试安排
POST /api/v1/human-loop/approve      # 图7: 人类确认
POST /api/v1/human-loop/stop         # 图7: 紧急停止

POST /api/v1/tools/email/send        # MCP邮件
GET  /api/v1/tools/calendar/query    # MCP日历
POST /api/v1/tools/calendar/book     # MCP预约

POST /api/v1/retrieval/search        # 向量检索
POST /api/v1/retrieval/embed         # 文本嵌入

POST /api/v1/memory/read             # 记忆读取
POST /api/v1/memory/write            # 记忆写入
```

---

> 本文档严格遵循 `AI_Recruitment_System_PRD.md` 的技术架构和业务需求制定。
> 所有实施步骤以 PRD 中的 7 种 AI Agent 架构模式和 11 页面映射为准。
