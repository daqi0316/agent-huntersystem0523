## 一、整体架构重设计

### 1.1 前后端分离总览
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端层 (Frontend)                                │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  React 18 + TypeScript + Vite + TailwindCSS + shadcn/ui            │ │
│  │                                                                       │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │ │
│  │  │ 任务管理  │  │ 候选人看板│  │ 数据分析  │  │ 系统配置  │            │ │
│  │  │  (Kanban)│  │ (DataGrid)│  │ (Charts) │  │ (Settings)│            │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │ │
│  │                                                                       │ │
│  │  状态管理: Zustand | 数据获取: TanStack Query | 表单: React Hook Form│ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                              ↑ REST API / WebSocket                        │
├──────────────────────────────┼──────────────────────────────────────────────┤
│                              │                                              │
│  ┌───────────────────────────▼───────────────────────────────────────────┐ │
│  │                        API 网关层 (Nginx / Traefik)                      │ │
│  │     路由 / 限流 / 认证 / CORS / 负载均衡 / SSL 终止                      │ │
│  └───────────────────────────┬───────────────────────────────────────────┘ │
│                              │                                              │
├──────────────────────────────┼──────────────────────────────────────────────┤
│                              │                                              │
│  ┌───────────────────────────▼───────────────────────────────────────────┐ │
│  │                     后端服务层 (Backend Services)                        │ │
│  │                                                                         │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │ │
│  │  │  用户服务       │  │  任务调度服务    │  │  候选人服务      │        │ │
│  │  │  (Auth/User)    │  │  (Celery/Redis) │  │  (CRUD/Search)  │        │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘        │ │
│  │                                                                         │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │ │
│  │  │  平台适配服务    │  │  AI 分析服务     │  │  通知服务        │        │ │
│  │  │  (Adapters)     │  │  (LLM Pipeline) │  │  (Email/Webhook)│        │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘        │ │
│  │                                                                         │ │
│  │  框架: FastAPI + Pydantic v2 | ORM: SQLAlchemy 2.0 + Alembic         │ │
│  │  异步: asyncio + Celery | 缓存: Redis | 搜索: Elasticsearch           │ │
│  └───────────────────────────┬───────────────────────────────────────────┘ │
│                              │                                              │
├──────────────────────────────┼──────────────────────────────────────────────┤
│                              │                                              │
│  ┌───────────────────────────▼───────────────────────────────────────────┐ │
│  │                     Agent 引擎层 (Agent Engine)                          │ │
│  │                                                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │ │
│  │  │                    编排层 (Orchestrator)                         │   │ │
│  │  │     意图识别 → 任务分解 → Agent 路由 → 结果聚合 → 状态管理        │   │ │
│  │  └─────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │ │
│  │  │ 搜索 Agent  │  │ 采集 Agent  │  │ 分析 Agent  │  │ 监控 Agent  │  │ │
│  │  │ (Search)    │  │ (Crawler)   │  │ (Analyzer)  │  │ (Watcher)   │  │ │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │ │
│  │         │                │                │                │         │ │
│  │         └────────────────┴────────────────┴────────────────┘         │ │
│  │                              │                                        │ │
│  │  ┌───────────────────────────▼────────────────────────────────────┐  │ │
│  │  │              共享层 (Shared Layer)                              │  │ │
│  │  │  记忆(Memory) / 知识(Knowledge) / 工具注册表(Tools) / 安全策略    │  │ │
│  │  └────────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────┬───────────────────────────────────────────┘ │
│                              │                                              │
├──────────────────────────────┼──────────────────────────────────────────────┤
│                              │                                              │
│  ┌───────────────────────────▼───────────────────────────────────────────┐ │
│  │                     MCP 工具层 (MCP Tools)                               │ │
│  │                                                                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │ │
│  │  │ Browser MCP │  │ Scraping MCP│  │ LLM MCP     │  │ Storage MCP │ │ │
│  │  │ (browser-use)│  │ (Scrapling) │  │ (多模型切换) │  │ (DB/Vector) │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │ │
│  │                                                                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │ │
│  │  │ Proxy MCP   │  │ Captcha MCP │  │ Notify MCP  │  │ Search MCP  │ │ │
│  │  │ (代理池)     │  │ (验证码处理) │  │ (消息推送)   │  │ (ES/向量)   │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                              │                                              │
├──────────────────────────────┼──────────────────────────────────────────────┤
│                              │                                              │
│  ┌───────────────────────────▼───────────────────────────────────────────┐ │
│  │                     基础设施层 (Infrastructure)                          │ │
│  │                                                                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │ │
│  │  │ PostgreSQL  │  │  Redis      │  │ Elasticsearch│  │  ChromaDB   │ │ │
│  │  │ (主数据库)   │  │ (缓存/队列)  │  │ (全文搜索)   │  │ (向量检索)   │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │ │
│  │                                                                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │ │
│  │  │ MinIO/S3    │  │ RabbitMQ    │  │ Prometheus  │  │  Grafana    │ │ │
│  │  │ (对象存储)   │  │ (消息队列)   │  │ (指标采集)   │  │ (监控面板)   │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

## 二、工程化设计

### 2.1 标准化项目结构
talent-sourcing-agent/
├── README.md
├── Makefile                    # 统一命令入口
├── docker-compose.yml          # 本地开发环境
├── docker-compose.prod.yml     # 生产环境
├── .env.example                # 环境变量模板
├── .gitignore
├── pyproject.toml              # Python 项目配置 (PEP 621)
├── pytest.ini                 # 测试配置
├── .pre-commit-config.yaml     # 代码提交前检查
├── .github/
│   └── workflows/
│       ├── ci.yml              # CI: 测试 + 代码质量
│       ├── cd.yml              # CD: 镜像构建 + 部署
│       └── release.yml       # 版本发布
│
├── frontend/                   # 前端项目 (独立仓库或子目录)
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   └── src/
│       ├── api/               # API 客户端 (OpenAPI 生成)
│       ├── components/        # 通用组件
│       ├── pages/             # 页面组件
│       ├── stores/            # Zustand 状态管理
│       ├── hooks/             # 自定义 Hooks
│       ├── types/             # TypeScript 类型
│       └── utils/             # 工具函数
│
├── backend/                    # 后端项目
│   ├── pyproject.toml
│   ├── alembic/               # 数据库迁移
│   │   ├── versions/
│   │   └── env.py
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI 入口
│   │   ├── config.py          # 配置管理 (Pydantic Settings)
│   │   ├── dependencies.py    # FastAPI 依赖注入
│   │   │
│   │   ├── api/               # API 路由层
│   │   │   ├── __init__.py
│   │   │   ├── v1/            # API 版本控制
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py    # 认证相关
│   │   │   │   ├── tasks.py   # 任务管理
│   │   │   │   ├── candidates.py
│   │   │   │   ├── platforms.py
│   │   │   │   ├── analytics.py
│   │   │   │   └── websocket.py
│   │   │   └── deps.py        # 通用依赖
│   │   │
│   │   ├── core/              # 核心框架
│   │   │   ├── __init__.py
│   │   │   ├── exceptions.py  # 自定义异常体系
│   │   │   ├── security.py    # JWT / 密码 / 权限
│   │   │   ├── pagination.py  # 统一分页
│   │   │   ├── response.py    # 统一响应格式
│   │   │   └── middleware.py  # 中间件 (日志/限流/追踪)
│   │   │
│   │   ├── models/            # 数据模型 (SQLAlchemy)
│   │   │   ├── __init__.py
│   │   │   ├── base.py        # 基类 + 通用字段
│   │   │   ├── user.py
│   │   │   ├── candidate.py
│   │   │   ├── task.py
│   │   │   ├── platform.py
│   │   │   └── log.py
│   │   │
│   │   ├── schemas/           # Pydantic 模型 (DTO)
│   │   │   ├── __init__.py
│   │   │   ├── base.py        # 基础 Schema
│   │   │   ├── user.py
│   │   │   ├── candidate.py
│   │   │   └── task.py
│   │   │
│   │   ├── services/          # 业务逻辑层
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── candidate_service.py
│   │   │   ├── task_service.py
│   │   │   └── platform_service.py
│   │   │
│   │   ├── repositories/      # 数据访问层 (Repository 模式)
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── candidate_repo.py
│   │   │   └── task_repo.py
│   │   │
│   │   ├── agent_engine/      # Agent 引擎
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py
│   │   │   ├── state_machine.py
│   │   │   ├── agents/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── search_agent.py
│   │   │   │   ├── crawl_agent.py
│   │   │   │   ├── analyze_agent.py
│   │   │   │   └── monitor_agent.py
│   │   │   └── shared/
│   │   │       ├── memory.py
│   │   │       ├── knowledge.py
│   │   │       └── tool_registry.py
│   │   │
│   │   ├── mcp/               # MCP 工具层
│   │   │   ├── __init__.py
│   │   │   ├── server.py      # MCP Server 入口
│   │   │   ├── tools/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── browser_tool.py
│   │   │   │   ├── scraping_tool.py
│   │   │   │   ├── llm_tool.py
│   │   │   │   ├── proxy_tool.py
│   │   │   │   └── storage_tool.py
│   │   │   └── adapters/
│   │   │       ├── __init__.py
│   │   │       ├── base.py
│   │   │       ├── boss_zhipin.py
│   │   │       ├── liepin.py
│   │   │       ├── maimai.py
│   │   │       ├── linkedin.py
│   │   │       └── github.py
│   │   │
│   │   ├── infrastructure/    # 基础设施
│   │   │   ├── __init__.py
│   │   │   ├── database.py    # DB 连接池
│   │   │   ├── redis.py       # Redis 客户端
│   │   │   ├── elasticsearch.py
│   │   │   ├── chromadb.py
│   │   │   ├── celery_app.py  # 异步任务
│   │   │   ├── storage.py     # 对象存储
│   │   │   └── monitoring.py  # 监控指标
│   │   │
│   │   └── utils/             # 工具函数
│   │       ├── __init__.py
│   │       ├── logger.py        # 结构化日志
│   │       ├── validators.py
│   │       └── helpers.py
│   │
│   └── tests/                 # 测试
│       ├── __init__.py
│       ├── conftest.py         # pytest fixtures
│       ├── unit/              # 单元测试
│       ├── integration/       # 集成测试
│       └── e2e/               # 端到端测试
│
├── docs/                       # 文档
│   ├── architecture/          # 架构文档
│   ├── api/                    # API 文档
│   ├── deployment/            # 部署文档
│   └── development/           # 开发指南
│
└── scripts/                    # 运维脚本
    ├── init_db.sh
    ├── backup.sh
    └── deploy.sh

### 2.2 代码质量与 CI/CD

**pyproject.toml 核心配置：**
[project]
name = "talent-sourcing-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "sqlalchemy>=2.0.35",
    "alembic>=1.13.0",
    "asyncpg>=0.29.0",           # PostgreSQL 异步驱动
    "redis>=5.0.0",
    "celery>=5.4.0",
    "elasticsearch>=8.15.0",
    "chromadb>=0.5.0",
    "browser-use>=0.1.0",
    "scrapling>=0.2.0",
    "httpx>=0.27.0",             # 异步 HTTP
    "structlog>=24.4.0",         # 结构化日志
    "prometheus-client>=0.21.0",
    "sentry-sdk>=2.0.0",         # 错误追踪
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",             # TestClient
    "ruff>=0.6.0",               # 代码格式化 + Lint
    "mypy>=1.11.0",              # 类型检查
    "pre-commit>=3.8.0",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

**.pre-commit-config.yaml：**
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        additional_dependencies: [types-redis]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

### 2.3 统一响应格式与异常体系
# backend/src/core/response.py
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T")

class APIResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: Optional[T] = None
    request_id: Optional[str] = None  # 链路追踪

class PaginationData(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: list[T]

class PaginationResponse(APIResponse[PaginationData[T]], Generic[T]):
    pass
# backend/src/core/exceptions.py
from fastapi import HTTPException, status

class BusinessException(Exception):
    """业务异常基类"""
    def __init__(self, code: int, message: str, details: dict = None):
        self.code = code
        self.message = message
        self.details = details or {}

class PlatformNotFoundError(BusinessException):
    def __init__(self, platform_id: str):
        super().__init__(
            code=404001,
            message=f"平台 {platform_id} 不存在或未启用",
            details={"platform_id": platform_id}
        )

class CrawlBlockedError(BusinessException):
    def __init__(self, platform: str, reason: str):
        super().__init__(
            code=429001,
            message=f"平台 {platform} 采集被拦截: {reason}",
            details={"platform": platform, "reason": reason}
        )

class RateLimitExceededError(BusinessException):
    def __init__(self, retry_after: int):
        super().__init__(
            code=429002,
            message="请求频率超限",
            details={"retry_after_seconds": retry_after}
        )

## 三、深度化设计

### 3.1 反爬对抗体系（深度）
┌─────────────────────────────────────────────────────────────┐
│                    反爬对抗引擎 (Anti-Crawl Engine)            │
├─────────────────────────────────────────────────────────────┤
│  第一层：指纹伪装层                                           │
│  ├── 浏览器指纹随机化 (Canvas/WebGL/Audio/Fonts)               │
│  ├── User-Agent 池 (500+ 真实 UA，按平台匹配)                 │
│  ├── 屏幕分辨率模拟 (常见分辨率池)                             │
│  ├── 时区/语言/地理位置匹配目标平台                            │
│  └── WebDriver 检测规避 (删除 navigator.webdriver)            │
├─────────────────────────────────────────────────────────────┤
│  第二层：行为模拟层                                           │
│  ├── 鼠标轨迹贝塞尔曲线模拟 (非直线移动)                        │
│  ├── 滚动速度随机化 (带加速/减速)                              │
│  ├── 点击位置正态分布 (非固定坐标)                             │
│  ├── 输入延迟模拟 (打字速度 80-200 WPM 随机)                   │
│  └── 页面停留时间随机化 (基于内容长度计算)                      │
├─────────────────────────────────────────────────────────────┤
│  第三层：请求调度层                                           │
│  ├── 代理池管理 (住宅代理 + 数据中心代理 + 移动代理)            │
│  ├── 智能限频 (根据平台响应动态调整间隔)                        │
│  ├── 请求时间窗口分散 (避免整点/半点集中请求)                    │
│  ├── 会话轮换 (Cookie/JWT 定期更换)                          │
│  └── 失败退避策略 (指数退避 + 抖动)                           │
├─────────────────────────────────────────────────────────────┤
│  第四层：验证码应对层                                         │
│  ├── 图像验证码：2Captcha / CapSolver 打码服务                 │
│  ├── 滑块验证码：轨迹模拟 + 缺口识别                           │
│  ├── 点击验证码：YOLO 目标检测                                 │
│  ├── reCAPTCHA：打码服务或人工介入                             │
│  └── 验证码触发监控 (成功率 < 80% 自动告警)                    │
├─────────────────────────────────────────────────────────────┤
│  第五层：账号安全层                                           │
│  ├── 多账号矩阵 (主号 + 备用号 + 采集号)                       │
│  ├── 账号健康度监控 (登录态/封禁状态/信用分)                    │
│  ├── 行为模式学习 (模拟真实用户浏览习惯)                        │
│  └── 账号轮换策略 (按平台风控等级动态分配)                      │
└─────────────────────────────────────────────────────────────┘

### 3.2 数据质量控制流水线
原始页面 HTML
    │
    ▼
┌─────────────────┐
│  第一层：解析校验  │  Scrapling 提取 + XPath/CSS 选择器验证
│  (结构完整性)     │  关键字段缺失率 > 30% → 标记待人工审核
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  第二层：数据清洗  │  手机号/邮箱格式校验 | 公司名标准化 | 去重
│  (格式标准化)     │  技能标签归一化 (NLP 同义词合并)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  第三层：交叉验证  │  同一候选人多平台数据比对 | 时间线一致性检查
│  (多源一致性)     │  矛盾数据标记 (如工作年限 vs 毕业时间)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  第四层：AI 增强   │  LLM 生成职业摘要 | 技能推断 | 匹配度评分
│  (智能补全)       │  置信度 < 0.7 的字段标记为"AI推测"
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  第五层：人工审核  │  高价值候选人强制人工确认 | 争议数据仲裁
│  (质量闭环)       │  审核结果反馈训练数据
└─────────────────┘

### 3.3 AI 分析深度链路
# backend/src/agent_engine/agents/analyze_agent.py
from typing import List, Optional
from pydantic import BaseModel, Field

class SkillAssessment(BaseModel):
    """技能评估"""
    skill_name: str
    proficiency: int = Field(ge=1, le=5, description="熟练度 1-5")
    evidence: str = Field(description="证据来源，如'3年Python经验+2个开源项目'")
    confidence: float = Field(ge=0, le=1)

class CareerTrajectory(BaseModel):
    """职业轨迹分析"""
    current_level: str = Field(description="当前职级，如P6/P7")
    trajectory: str = Field(description="上升/平稳/下降")
    stability_score: float = Field(ge=0, le=100, description="稳定性评分")
    red_flags: List[str] = Field(default_factory=list, description="风险标记")

class MatchAnalysis(BaseModel):
    """岗位匹配分析"""
    overall_score: float = Field(ge=0, le=100)
    dimension_scores: dict[str, float]  # 技能/经验/学历/薪资/文化
    strengths: List[str]
    gaps: List[str]
    recommendation: str = Field(description="强烈推荐/推荐/谨慎考虑/不推荐")

class CandidateAnalysisResult(BaseModel):
    """候选人分析结果 (结构化输出，用于前端展示)"""
    candidate_id: str
    analysis_version: str = "v2.1"
    
    # 技能分析
    skills: List[SkillAssessment]
    skill_vector: List[float]  # 嵌入向量，用于相似度搜索
    
    # 职业分析
    career: CareerTrajectory
    work_history_summary: str
    
    # 匹配分析
    match: Optional[MatchAnalysis] = None  # 需绑定 JD 后生成
    
    # 原始数据质量
    data_quality_score: float
    ai_confidence: float
    
    # 元数据
    analyzed_at: str
    analyzer_model: str

## 四、长远化设计

### 4.1 微服务拆分路线图
Phase 1 (当前): 单体架构
┌─────────────────────────────────────┐
│  FastAPI 单体 (所有模块在一个进程)    │
└─────────────────────────────────────┘

Phase 2 (6个月后): 核心服务拆分
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  API Gateway │ │  Task Svc   │ │  Candidate  │
│  (Kong/Traefik)│  (Celery)   │ │  Svc        │
└─────────────┘ └─────────────┘ └─────────────┘
       │              │              │
       └──────────────┴──────────────┘
                      │
              ┌───────▼───────┐
              │  Shared DB    │
              │  (PostgreSQL) │
              └───────────────┘

Phase 3 (12个月后): 完整微服务
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│  Gateway│ │  User   │ │  Task   │ │Candidate│ │ Platform│
│         │ │  Svc    │ │  Svc    │ │  Svc    │ │  Svc    │
└────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
     │           │           │           │           │
     └───────────┴───────────┴───────────┴───────────┘
                         │
              ┌──────────▼──────────┐
              │   Service Mesh      │
              │   (Istio/Linkerd)   │
              └──────────┬──────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ┌─────────┐    ┌─────────┐    ┌─────────┐
   │  User DB │    │  Task DB │    │Candidate│
   │(PostgreSQL)│   │(Redis+PG)│   │  DB+ES  │
   └─────────┘    └─────────┘    └─────────┘
### 4.2 多租户 SaaS 化预留
# backend/src/models/base.py
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import declarative_base, declared_attr
from datetime import datetime

class TenantMixin:
    """多租户混入类 — 所有业务表继承"""
    
    @declared_attr
    def tenant_id(cls):
        return Column(String(64), nullable=False, index=True, comment="租户ID")
    
    @declared_attr
    def created_by(cls):
        return Column(String(64), nullable=False, comment="创建者")
    
    @declared_attr
    def updated_by(cls):
        return Column(String(64), nullable=True, comment="更新者")

class TimestampMixin:
    """时间戳混入类"""
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

Base = declarative_base()

class TenantAwareBase(Base, TenantMixin, TimestampMixin):
    """所有业务模型的基类"""
    __abstract__ = True

### 4.3 合规审计体系
# backend/src/models/log.py
class AuditLog(Base):
    """操作审计日志 — 不可删除，用于合规"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    
    # 操作信息
    action = Column(String(50), nullable=False, comment="操作类型: CREATE/READ/UPDATE/DELETE/EXPORT")
    resource_type = Column(String(50), nullable=False, comment="资源类型: candidate/task/platform")
    resource_id = Column(String(100), nullable=False, comment="资源ID")
    
    # 操作人
    user_id = Column(String(64), nullable=False)
    user_email = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(Text, nullable=True)
    
    # 变更详情 (JSON Diff)
    before_data = Column(JSON, nullable=True, comment="变更前数据")
    after_data = Column(JSON, nullable=True, comment="变更后数据")
    
    # 合规标记
    data_sensitivity = Column(String(20), default="normal", comment="数据敏感度: normal/high/critical")
    gdpr_purpose = Column(String(100), nullable=True, comment="数据处理目的")
    consent_reference = Column(String(100), nullable=True, comment="用户授权编号")
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_audit_logs_tenant_action", "tenant_id", "action", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
    )
## 五、模块化设计

### 5.1 平台适配器插件体系
# backend/src/mcp/adapters/base.py
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from pydantic import BaseModel, ConfigDict
from enum import Enum

class PlatformStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # 响应慢但可用
    BLOCKED = "blocked"      # 需要验证码
    DOWN = "down"            # 完全不可用

class CrawlResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    success: bool
    candidates: list[dict] = []
    raw_html: Optional[str] = None
    error_message: Optional[str] = None
    next_page_url: Optional[str] = None
    rate_limit_info: Optional[dict] = None  # 限流信息，用于智能调度
    fingerprint_used: Optional[str] = None   # 使用的指纹ID，用于追踪

class PlatformAdapter(ABC):
    """平台适配器基类 — 所有平台必须实现"""
    
    # 类属性：平台元数据
    name: str                    # 平台标识，如 "boss_zhipin"
    display_name: str            # 显示名称，如 "BOSS直聘"
    category: str                # 平台分类：job_board / social / code / academic
    anti_crawl_level: int        # 反爬等级 1-5
    requires_login: bool
    supports_realtime: bool      # 是否支持实时搜索
    
    def __init__(self, config: dict, proxy_pool, fingerprint_manager):
        self.config = config
        self.proxy_pool = proxy_pool
        self.fingerprint_manager = fingerprint_manager
        self._health_status = PlatformStatus.HEALTHY
        self._consecutive_failures = 0
    
    @abstractmethod
    async def health_check(self) -> PlatformStatus:
        """健康检查：快速探测平台可用性"""
        pass
    
    @abstractmethod
    async def search(self, keyword: str, filters: dict = None) -> CrawlResult:
        """关键词搜索：返回候选人列表页"""
        pass
    
    @abstractmethod
    async def get_detail(self, candidate_url: str) -> CrawlResult:
        """获取候选人详情页"""
        pass
    
    @abstractmethod
    async def parse_list_page(self, html: str) -> list[dict]:
        """解析列表页：提取候选人摘要信息"""
        pass
    
    @abstractmethod
    async def parse_detail_page(self, html: str) -> dict:
        """解析详情页：提取完整候选人信息"""
        pass
    
    # 通用方法（可覆盖）
    async def pre_search(self, keyword: str) -> None:
        """搜索前钩子：如预热浏览器、检查登录态"""
        pass
    
    async def post_search(self, result: CrawlResult) -> CrawlResult:
        """搜索后钩子：如数据清洗、格式统一"""
        return result
    
    @property
    def health_status(self) -> PlatformStatus:
        return self._health_status
    
    def record_failure(self):
        """记录失败，用于健康度评估"""
        self._consecutive_failures += 1
        if self._consecutive_failures >= 5:
            self._health_status = PlatformStatus.DOWN
        elif self._consecutive_failures >= 2:
            self._health_status = PlatformStatus.DEGRADED
    
    def record_success(self):
        """记录成功"""
        self._consecutive_failures = 0
        self._health_status = PlatformStatus.HEALTHY

**平台适配器注册表（自动发现）：**
# backend/src/mcp/adapters/__init__.py
import importlib
import pkgutil
from typing import Type

from .base import PlatformAdapter

# 自动发现所有适配器
_ADAPTERS: dict[str, Type[PlatformAdapter]] = {}

def discover_adapters():
    """自动扫描并注册所有平台适配器"""
    package = __package__ or "backend.src.mcp.adapters"
    for _, name, _ in pkgutil.iter_modules(__path__):
        if name.startswith("_") or name == "base":
            continue
        module = importlib.import_module(f".{name}", package)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, PlatformAdapter) and 
                attr is not PlatformAdapter and
                hasattr(attr, "name")):
                _ADAPTERS[attr.name] = attr
                print(f"✅ 注册平台适配器: {attr.name} ({attr.display_name})")

def get_adapter(name: str) -> Type[PlatformAdapter]:
    if name not in _ADAPTERS:
        raise PlatformNotFoundError(name)
    return _ADAPTERS[name]

def list_adapters() -> list[dict]:
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name,
            "category": cls.category,
            "anti_crawl_level": cls.anti_crawl_level,
            "requires_login": cls.requires_login,
        }
        for cls in _ADAPTERS.values()
    ]

# 模块导入时自动发现
discover_adapters()

### 5.2 可插拔 LLM 设计
# backend/src/mcp/tools/llm_tool.py
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from enum import Enum
import openai
import httpx

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"           # 阿里云
    LOCAL = "local"         # ollama/omlx 本地模型

class LLMConfig(BaseModel):
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 60
    
    # 本地模型特殊配置
    local_framework: Optional[str] = None  # "ollama" / "omlx"
    local_model_path: Optional[str] = None

class BaseLLM(ABC):
    """LLM 基类"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
    
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """非流式对话"""
        pass
    
    @abstractmethod
    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        """流式对话"""
        pass
    
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """获取文本嵌入向量"""
        pass

class OpenAILLM(BaseLLM):
    """OpenAI / 兼容 OpenAI API 的提供商"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.client = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout),
        )
    
    async def chat(self, messages: list[dict], **kwargs) -> str:
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            **kwargs
        )
        return response.choices[0].message.content
    
    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            stream=True,
            **kwargs
        )
        async for chunk in stream:
            if content := chunk.choices[0].delta.content:
                yield content
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [item.embedding for item in response.data]

class LocalLLM(BaseLLM):
    """本地模型 (omlx / ollama)"""
    
    async def chat(self, messages: list[dict], **kwargs) -> str:
        if self.config.local_framework == "omlx":
            # omlx 推理框架适配
            import mlx_lm
            # ... 具体实现
            pass
        elif self.config.local_framework == "ollama":
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.config.base_url}/api/chat",
                    json={
                        "model": self.config.model,
                        "messages": messages,
                        "stream": False,
                    }
                )
                return response.json()["message"]["content"]
        else:
            raise ValueError(f"不支持的本地框架: {self.config.local_framework}")
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 本地嵌入模型，如 bge-m3
        pass

class LLMFactory:
    """LLM 工厂 — 根据配置创建对应实例"""
    
    _registry = {
        LLMProvider.OPENAI: OpenAILLM,
        LLMProvider.ANTHROPIC: OpenAILLM,  # Anthropic 也兼容 OpenAI 格式
        LLMProvider.DEEPSEEK: OpenAILLM,
        LLMProvider.QWEN: OpenAILLM,
        LLMProvider.LOCAL: LocalLLM,
    }
    
    @classmethod
    def create(cls, config: LLMConfig) -> BaseLLM:
        llm_class = cls._registry.get(config.provider)
        if not llm_class:
            raise ValueError(f"不支持的 LLM 提供商: {config.provider}")
        return llm_class(config)

## 六、可扩展设计

### 6.1 异步任务与消息队列
# backend/src/infrastructure/celery_app.py
from celery import Celery
from celery.signals import task_failure, task_success
import structlog

logger = structlog.get_logger()

celery_app = Celery(
    "talent_sourcing",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
    include=[
        "src.services.tasks.crawl_task",
        "src.services.tasks.analyze_task",
        "src.services.tasks.export_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,           # 任务最长运行1小时
    worker_prefetch_multiplier=1,   # 公平调度，避免 worker 饿死
    task_acks_late=True,            # 任务完成后才确认
    worker_max_tasks_per_child=50,  # 防止内存泄漏
)

# 任务失败告警
@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    logger.error(
        "任务执行失败",
        task_id=task_id,
        task_name=sender.name if sender else "unknown",
        error=str(exception),
    )
    # TODO: 发送钉钉/企业微信告警

@task_success.connect
def handle_task_success(sender=None, result=None, **kwargs):
    logger.info(
        "任务执行成功",
        task_name=sender.name if sender else "unknown",
    )

**核心任务定义：**
# backend/src/services/tasks/crawl_task.py
from celery import shared_task, chord, group
from celery.exceptions import MaxRetriesExceededError
from datetime import datetime

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
)
def crawl_platform_task(self, platform_name: str, keyword: str, task_id: str, filters: dict = None):
    """单个平台采集任务"""
    from src.mcp.adapters import get_adapter
    from src.services.task_service import TaskService
    
    task_service = TaskService()
    task_service.update_status(task_id, "running", platform=platform_name)
    
    try:
        adapter_class = get_adapter(platform_name)
        adapter = adapter_class(
            config=get_platform_config(platform_name),
            proxy_pool=get_proxy_pool(),
            fingerprint_manager=get_fingerprint_manager(),
        )
        
        # 执行搜索
        result = adapter.search(keyword, filters)
        
        # 存储结果
        candidates = []
        for candidate_data in result.candidates:
            candidate = save_candidate(candidate_data, source_platform=platform_name)
            candidates.append(candidate.id)
        
        # 触发分析任务
        if candidates:
            analyze_candidates_task.delay(candidates, task_id)
        
        task_service.update_status(
            task_id, "completed", 
            platform=platform_name,
            candidates_found=len(candidates)
        )
        
        return {
            "platform": platform_name,
            "candidates_found": len(candidates),
            "candidate_ids": candidates,
        }
        
    except Exception as exc:
        # 指数退避重试
        retry_count = self.request.retries
        backoff = min(2 ** retry_count * 60, 3600)  # 最大1小时
        raise self.retry(exc=exc, countdown=backoff)

@shared_task
def multi_platform_crawl_task(platforms: list[str], keyword: str, task_id: str):
    """多平台并行采集 — 使用 Celery chord 模式"""
    # 创建并行任务组
    job = group(
        crawl_platform_task.s(platform, keyword, task_id)
        for platform in platforms
    )
    
    # 所有平台完成后，执行聚合
    result = chord(job)(aggregate_results_task.s(task_id))
    return result.id

@shared_task
def aggregate_results_task(results: list[dict], task_id: str):
    """聚合多平台结果，去重"""
    from src.services.candidate_service import CandidateService
    
    all_candidates = []
    for result in results:
        all_candidates.extend(result.get("candidate_ids", []))
    
    # 去重逻辑
    deduped = CandidateService.deduplicate(all_candidates)
    
    return {
        "task_id": task_id,
        "total_found": len(all_candidates),
        "after_dedup": len(deduped),
        "duplicates_removed": len(all_candidates) - len(deduped),
    }

### 6.2 缓存与性能优化
# backend/src/infrastructure/redis.py
import redis.asyncio as redis
from functools import wraps
import json
import hashlib

class CacheManager:
    """多级缓存管理"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.local_cache = {}  # L1: 进程内缓存 (TTL 60s)
        self.default_ttl = 300  # L2: Redis 缓存 (TTL 5min)
    
    def cached(self, ttl: int = None, key_prefix: str = ""):
        """装饰器：自动缓存函数结果"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 生成缓存键
                cache_key = self._make_key(key_prefix, func.__name__, args, kwargs)
                
                # L1 检查
                if cache_key in self.local_cache:
                    return self.local_cache[cache_key]
                
                # L2 检查
                cached = await self.redis.get(cache_key)
                if cached:
                    result = json.loads(cached)
                    self.local_cache[cache_key] = result
                    return result
                
                # 执行并缓存
                result = await func(*args, **kwargs)
                
                # 写入缓存
                self.local_cache[cache_key] = result
                await self.redis.setex(
                    cache_key, 
                    ttl or self.default_ttl, 
                    json.dumps(result, default=str)
                )
                
                return result
            return wrapper
        return decorator
    
    def _make_key(self, prefix: str, func_name: str, args, kwargs) -> str:
        key_data = f"{func_name}:{args}:{sorted(kwargs.items())}"
        hash_val = hashlib.md5(key_data.encode()).hexdigest()[:12]
        return f"tsa:cache:{prefix}:{hash_val}"

# 使用示例
cache = CacheManager(redis_client)

@cache.cached(ttl=600, key_prefix="candidate")
async def get_candidate_detail(candidate_id: str):
    # 复杂查询...
    pass

## 七、前后端分离详细设计

### 7.1 API 设计规范 (RESTful + OpenAPI)
# backend/src/api/v1/candidates.py
from fastapi import APIRouter, Depends, Query, status
from typing import Optional, Literal
from src.schemas.candidate import (
    CandidateCreate, 
    CandidateResponse, 
    CandidateListResponse,
    CandidateSearchFilters,
    CandidateUpdate,
)
from src.services.candidate_service import CandidateService
from src.dependencies import get_current_user, get_db, require_permission

router = APIRouter(prefix="/candidates", tags=["候选人管理"])

@router.get(
    "",
    response_model=CandidateListResponse,
    summary="候选人列表",
    description="支持分页、筛选、排序的候选人查询接口",
)
async def list_candidates(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    platform: Optional[str] = Query(None, description="来源平台筛选"),
    status: Optional[Literal["new", "reviewed", "contacted", "archived"]] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    sort_by: Literal["created_at", "match_score", "experience_years"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    获取候选人列表，支持：
    - 全文搜索 (Elasticsearch)
    - 向量相似度搜索 (ChromaDB)
    - 多字段组合筛选
    - 智能排序
    """
    service = CandidateService(db)
    return await service.list(
        page=page,
        page_size=page_size,
        filters=CandidateSearchFilters(
            keyword=keyword,
            platform=platform,
            status=status,
            min_score=min_score,
        ),
        sort_by=sort_by,
        sort_order=sort_order,
        tenant_id=current_user.tenant_id,
    )

@router.get(
    "/{candidate_id}",
    response_model=CandidateResponse,
    summary="候选人详情",
)
async def get_candidate(
    candidate_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取单个候选人完整信息，包含 AI 分析结果"""
    service = CandidateService(db)
    return await service.get_detail(candidate_id, tenant_id=current_user.tenant_id)

@router.post(
    "/{candidate_id}/analyze",
    response_model=dict,
    summary="触发 AI 分析",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_analysis(
    candidate_id: str,
    jd_id: Optional[str] = None,
    db=Depends(get_db),
    current_user=Depends(require_permission("candidate:analyze")),
):
    """
    异步触发候选人 AI 分析任务
    - 如提供 jd_id，则生成岗位匹配分析
    - 如未提供，则生成通用职业分析
    """
    from src.services.tasks.analyze_task import analyze_candidate_task
    
    task = analyze_candidate_task.delay(
        candidate_id=candidate_id,
        jd_id=jd_id,
        requested_by=current_user.id,
    )
    
    return {
        "task_id": task.id,
        "status": "queued",
        "message": "分析任务已提交，请通过 WebSocket 或轮询获取结果",
    }

@router.get(
    "/{candidate_id}/analysis-stream",
    summary="AI 分析流式输出",
)
async def analysis_stream(
    candidate_id: str,
    ws=Depends(get_websocket),
):
    """WebSocket 流式返回 AI 分析过程"""
    # 实现 SSE 或 WebSocket 流式输出
    pass

### 7.2 前端架构
// frontend/src/api/client.ts
import axios, { AxiosInstance, AxiosError } from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

class APIClient {
  private client: AxiosInstance;
  
  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    // 请求拦截器：自动附加 Token
    this.client.interceptors.request.use((config) => {
      const token = localStorage.getItem('access_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });
    
    // 响应拦截器：统一错误处理
    this.client.interceptors.response.use(
      (response) => response.data,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          // Token 过期，跳转登录
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }
  
  // 候选人相关
  async getCandidates(params: CandidateListParams): Promise<CandidateListResponse> {
    return this.client.get('/candidates', { params });
  }
  
  async getCandidate(id: string): Promise<CandidateResponse> {
    return this.client.get(`/candidates/${id}`);
  }
  
  async triggerAnalysis(candidateId: string, jdId?: string) {
    return this.client.post(`/candidates/${candidateId}/analyze`, { jd_id: jdId });
  }
  
  // WebSocket 连接（任务实时状态）
  connectTaskWebSocket(taskId: string, onMessage: (data: any) => void) {
    const ws = new WebSocket(`ws://localhost:8000/ws/tasks/${taskId}`);
    ws.onmessage = (event) => onMessage(JSON.parse(event.data));
    return ws;
  }
}

export const api = new APIClient();

// frontend/src/stores/taskStore.ts
import { create } from 'zustand';
import { api } from '@/api/client';

interface TaskState {
  tasks: Task[];
  activeTask: Task | null;
  wsConnection: WebSocket | null;
  
  // Actions
  createTask: (params: CreateTaskParams) => Promise<void>;
  subscribeTask: (taskId: string) => void;
  unsubscribeTask: () => void;
  updateTaskStatus: (taskId: string, status: TaskStatus) => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: [],
  activeTask: null,
  wsConnection: null,
  
  createTask: async (params) => {
    const response = await api.post('/tasks', params);
    const task = response.data;
    set((state) => ({ tasks: [task, ...state.tasks] }));
    get().subscribeTask(task.id);
  },
  
  subscribeTask: (taskId: string) => {
    // 关闭旧连接
    get().unsubscribeTask();
    
    const ws = api.connectTaskWebSocket(taskId, (data) => {
      set((state) => ({
        tasks: state.tasks.map((t) =>
          t.id === taskId ? { ...t, ...data } : t
        ),
      }));
    });
    
    set({ wsConnection: ws });
  },
  
  unsubscribeTask: () => {
    const ws = get().wsConnection;
    if (ws) {
      ws.close();
      set({ wsConnection: null });
    }
  },
  
  updateTaskStatus: (taskId, status) => {
    set((state) => ({
      tasks: state.tasks.map((t) =>
        t.id === taskId ? { ...t, status } : t
      ),
    }));
  },
}));

## 八、数据库 Schema 升级

### 8.1 完整 ER 图设计
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│     users       │       │    tenants      │       │  tenant_plans   │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │◄──────│ id (PK)         │◄──────│ id (PK)         │
│ tenant_id (FK)  │       │ name            │       │ tenant_id (FK)  │
│ email           │       │ status          │       │ plan_type       │
│ role            │       │ created_at      │       │ max_tasks_month │
│ permissions     │       │ quota_limits    │       │ expires_at      │
└─────────────────┘       └─────────────────┘       └─────────────────┘
         │
         │
         ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  crawl_tasks    │◄─────│ task_platforms  │       │  candidates     │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ task_id (FK)    │       │ id (PK)         │
│ tenant_id (FK)  │       │ platform_name   │       │ tenant_id (FK)  │
│ created_by (FK) │       │ status          │       │ task_id (FK)    │
│ keyword         │       │ candidates_count│       │ name            │
│ status          │       │ error_log       │       │ platform_sources│
│ total_found     │       │ started_at      │       │ current_company │
│ after_dedup     │       │ finished_at     │       │ match_score     │
│ config          │       └─────────────────┘       │ skills_vector   │
│ created_at      │                                 │ analysis_result │
└─────────────────┘                                 │ status          │
         │                                          └─────────────────┘
         │                                                   │
         │                                                   │
         ▼                                                   ▼
┌─────────────────┐                                 ┌─────────────────┐
│  crawl_logs     │                                 │ candidate_platforms
├─────────────────┤                                 ├─────────────────┤
│ id (PK)         │                                 │ id (PK)         │
│ task_id (FK)    │                                 │ candidate_id(FK)│
│ platform        │                                 │ platform_name   │
│ url             │                                 │ platform_url    │
│ status          │                                 │ raw_data        │
│ candidates_found│                                 │ parsed_data     │
│ error_message   │                                 │ first_seen      │
│ duration_sec    │                                 │ last_verified   │
└─────────────────┘                                 └─────────────────┘
         │
         │
         ▼
┌─────────────────┐
│  audit_logs     │
├─────────────────┤
│ id (PK)         │
│ tenant_id       │
│ action          │
│ resource_type   │
│ resource_id     │
│ user_id         │
│ before_data     │
│ after_data      │
│ created_at      │
└─────────────────┘

### 8.2 SQLAlchemy 模型
# backend/src/models/candidate.py
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, 
    JSON, ForeignKey, Index, ARRAY
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector  # 需要 pgvector 扩展

from .base import TenantAwareBase

class Candidate(TenantAwareBase):
    __tablename__ = "candidates"
    
    id = Column(String(64), primary_key=True, default=generate_ulid)
    task_id = Column(String(64), ForeignKey("crawl_tasks.id"), nullable=True)
    
    # 基础信息
    name = Column(String(100), nullable=False, index=True)
    gender = Column(String(10), nullable=True)
    age = Column(Integer, nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    location = Column(String(100), nullable=True)
    
    # 职业信息
    current_company = Column(String(200), nullable=True, index=True)
    current_title = Column(String(200), nullable=True, index=True)
    experience_years = Column(Integer, nullable=True)
    salary_expectation = Column(Integer, nullable=True)  # 单位：千元/月
    
    # 技能与摘要
    skills = Column(ARRAY(String), default=list, comment="技能标签数组")
    skills_vector = Column(Vector(1536), nullable=True, comment="技能嵌入向量")
    summary = Column(Text, nullable=True, comment="AI 生成的职业摘要")
    
    # 匹配评分
    match_score = Column(Float, default=0, comment="通用匹配度 0-100")
    match_details = Column(JSON, default=dict, comment="各维度评分详情")
    
    # 来源信息
    platform_sources = Column(JSON, default=list, comment="多平台来源信息")
    primary_source = Column(String(50), nullable=False, index=True)
    
    # AI 分析结果
    analysis_result = Column(JSON, nullable=True, comment="完整 AI 分析结果")
    analysis_version = Column(String(20), nullable=True)
    analyzed_at = Column(DateTime, nullable=True)
    
    # 状态管理
    status = Column(String(20), default="new", index=True)
    tags = Column(ARRAY(String), default=list)
    notes = Column(Text, nullable=True)
    
    # 关联
    task = relationship("CrawlTask", back_populates="candidates")
    platform_data = relationship("CandidatePlatform", back_populates="candidate")
    
    __table_args__ = (
        Index("ix_candidates_tenant_score", "tenant_id", "match_score"),
        Index("ix_candidates_tenant_status", "tenant_id", "status"),
        Index("ix_candidates_skills_gin", "skills", postgresql_using="gin"),
    )

## 九、部署架构

### 9.1 Docker Compose 开发环境
# docker-compose.yml
version: "3.8"

services:
  # 后端 API
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/talent_sourcing
      - REDIS_URL=redis://redis:6379/0
      - ELASTICSEARCH_URL=http://elasticsearch:9200
    volumes:
      - ./backend/src:/app/src
    depends_on:
      - db
      - redis
      - elasticsearch

  # 前端
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    volumes:
      - ./frontend/src:/app/src
    environment:
      - VITE_API_URL=http://localhost:8000/api/v1

  # Celery Worker
  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A src.infrastructure.celery_app worker -l info -Q crawl,analyze,export
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/talent_sourcing
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis

  # Celery Beat (定时任务)
  beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A src.infrastructure.celery_app beat -l info
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

  # 数据库
  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=talent_sourcing
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  # Elasticsearch
  elasticsearch:
    image: elasticsearch:8.15.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ports:
      - "9200:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data

  # ChromaDB (向量数据库)
  chromadb:
    image: chromadb/chroma:0.5.0
    ports:
      - "8001:8000"
    volumes:
      - chroma_data:/chroma/chroma

volumes:
  postgres_data:
  redis_data:
  es_data:
  chroma_data:

### 9.2 生产环境 Kubernetes 部署
# k8s/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: talent-sourcing-backend
  labels:
    app: backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
        - name: backend
          image: registry.example.com/talent-sourcing/backend:v1.0.0
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: url
            - name: REDIS_URL
              valueFrom:
                configMapKeyRef:
                  name: app-config
                  key: redis_url
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2000m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: backend-service
spec:
  selector:
    app: backend
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP

## 十、实施路线图
| 阶段          | 周期    | 目标          | 关键交付物                           |
| ----------- | ----- | ----------- | ------------------------------- |
| **Phase 0** | 1-2 周 | 项目骨架 + 开发环境 | 完整项目结构、Docker Compose、CI/CD 流水线 |
| **Phase 1** | 2-3 周 | BOSS直聘 MVP  | 单个平台完整采集、数据库存储、基础 API           |
| **Phase 2** | 2-3 周 | 前端 + 多平台    | React 前端、猎聘/脉脉适配、任务调度           |
| **Phase 3** | 2-3 周 | AI 分析 + 搜索  | LLM 集成、ES 全文搜索、向量相似度            |
| **Phase 4** | 2-3 周 | 工程化完善       | 测试覆盖、监控告警、文档、性能优化               |
| **Phase 5** | 持续    | 迭代扩展        | 新平台适配、SaaS 化、商业化                |

这份方案将原来的单体脚本升级为**企业级工程架构**，具备以下特点：

1. **工程化**：标准化项目结构、CI/CD、代码质量工具、测试体系
    
2. **深度化**：五层反爬对抗、五级数据质量控制、结构化 AI 分析
    
3. **长远化**：微服务拆分路线、多租户预留、合规审计
    
4. **模块化**：插件式平台适配、可插拔 LLM、独立 MCP 工具
    
5. **可扩展**：消息队列、多级缓存、水平扩展、K8s 部署
    
6. **前后端分离**：FastAPI + React/TypeScript，RESTful API + WebSocket 实时通信
    

需要我把某个模块（如前端组件设计、K8s 完整配置、具体平台适配器实现）进一步展开吗？

