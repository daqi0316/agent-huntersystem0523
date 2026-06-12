# 寻源 Agent 重构规划 v4 — 自审核修正版

> 基于 Momus 审核发现的 12 项问题修正
> 修正重点：反爬现实主义、架构瘦身、任务队列可靠、去重策略具体化、时间线调整

---

## 目录

1. [现状与问题](#一现状与问题)
2. [技术选型（修正版 v4）](#二技术选型修正版-v4)
3. [整体架构](#三整体架构)
4. [模块结构](#四模块结构)
5. [数据模型](#五数据模型)
6. [去重策略](#六去重策略)
7. [账号管理体系](#七账号管理体系)
8. [反爬对抗（现实主义版）](#八反爬对抗现实主义版)
9. [错误分类与恢复](#九错误分类与恢复)
10. [增量采集策略](#十增量采集策略)
11. [异步任务体系](#十一异步任务体系)
12. [API 设计](#十二api-设计)
13. [前端设计](#十三前端设计)
14. [隐私合规](#十四隐私合规)
15. [测试策略](#十五测试策略)
16. [可观测性](#十六可观测性)
17. [实施路线图](#十七实施路线图)
18. [关键设计决策](#十八关键设计决策)
19. [成本估算（修正版）](#十九成本估算修正版)

---

## 一、现状与问题

### 现有 SourcingAgent（不动）

`apps/api/app/agents/sourcing_agent.py` 是**逻辑型寻源助手**，能力：
- 人才 Mapping（LLM + 规则兜底）
- 渠道策略推荐
- 触达话术生成
- JD 生成（代理至 JDGeneratorService）

**保持不动**，只在其上叠加数据采集层。

### 缺失的核心能力

- ❌ 无真实爬虫能力——搜不到真实候选人
- ❌ 无平台适配层——不能对接 BOSS/猎聘等
- ❌ 无可靠异步任务队列——asyncio.create_task 在进程重启时丢失
- ❌ 无反爬对抗——中文平台反爬极严（BOSS直聘 4/5 级）
- ❌ 无数据质量链路——采集的数据没校验
- ❌ 无账号管理体系——无 Cookie 持久化/配额跟踪/封号检测
- ❌ 无增量采集——每次全量重爬

### 可复用的现有资产

- ✅ 完整的 Agent 框架（`BaseAgent` / `AgentRegistry` / `PipelineAgent`）
- ✅ Candidate 模型 + CRUD API + 时间线系统
- ✅ Next.js 前端架构 + Tailwind + shadcn/ui
- ✅ 基础设施（PostgreSQL / Redis / Qdrant / MinIO）
- ✅ 工程规范（pre-commit / ruff / mypy / health-check）

---

## 二、技术选型（修正版 v4）

### v3 → v4 关键修正

| 问题 | v3 判断 | v4 修正 |
|------|---------|---------|
| BOSS直聘反爬 | Scrapling StealthyFetcher 可应对 | 需 CDP Chrome + 真实账号 + Cookie 持久化 为基线。Scrapling StealthyFetcher 只作为 HTTP 层增强 |
| Scrapling adaptive 预期 | 平台改版自动恢复 | 对动态类名（BOSS直聘）作用有限，自适应解析主要针对结构稳定的页面（GitHub、知乎静态页） |
| 任务队列 | P0-P2 用 asyncio + Redis Stream | P0 就用 **arq**（轻量 Redis 队列），不引入 Celery 但也不丢失任务 |
| 架构分层 | services/ + agents/ + tasks/ 三层 | P0-P2 **合并为一层**：sourcing/orchestrator.py。P4+ 再引入 Agent 层 |

### 最终技术栈

| 层 | 选型 | 角色 |
|----|------|------|
| **主爬取引擎** | Scrapling (FetcherSession + StealthyFetcher) | HTTP 级批量并发采集，反爬指纹伪装 |
| **复杂交互** | Playwright CDP（python） + 真实浏览器 | BOSS直聘登录、验证码、Cookie 维护。**基线方案** |
| **浏览器自动化** | Playwright（直接，非 browser-use） | 渲染 JS、登录态管理 |
| **异步任务** | **arq**（P0+） → 非必要不升级 Celery | 基于 Redis 的轻量异步队列，任务持久化不丢失 |
| **自适应解析** | Scrapling `adaptive`（有限使用） | GitHub/知乎等静态结构页面有效 |
| **向量搜索** | Qdrant（已有） | 技能语义搜索 |
| **LLM 分析** | 现有 LLM 客户端复用 | 复用已有的多模型切换 |
| **前端** | Next.js 14 + Tailwind（已有） | 与现有系统一致 |
| **反爬引擎** | 自研代理层 + Scrapling 指纹 + Playwright CDP | 三层叠加 |
| **代理池** | 住宅代理（P0 即需） | P0 测试也需要代理，不要直连 |
| **站点经验** | JSON 文件按域名存储 | web-access 模式 |

### Scrapling 与 browser-use 的角色重新定义

```
v3 问题：让 Scrapling 独担 BOSS直聘反爬，不现实

v4 修正：

非交互式采集（GitHub API、猎聘列表页、知乎） → Scrapling HTTP Fetcher
交互式采集（BOSS直聘搜索、翻页、详情）    → Playwright CDP + Cookie 持久化
验证码/复杂登录                           → Playwright CDP（人工介入 or 打码服务）
LLM 分析                                  → 现有 LLM 客户端

browser-use 不引入。理由：
  1. 每步调 LLM 对爬虫场景无意义
  2. BOSS直聘的交互模式是固定的（搜索→翻页→点开），不需要 LLM 决策
  3. 直接 Playwright CDP 写固定逻辑，更可控、更快、零 API 成本
```

### 为什么不直接 broom（Scrapling）？

Scrapling 的 `StealthyFetcher` 在内置 Cloudflare Turnstile 绕过方面确实有优势，但：
- BOSS直聘的验证不仅是 Cloudflare，还有行为分析、设备指纹、账号行为评分
- HTTP 层无法模拟真实的鼠标轨迹、滚动、点击间隔
- Scrapling 的 `DynamicFetcher` 底层也是 Playwright，不如直接用 Playwright CDP
- **策略**：Scrapling 做轻量级/低反爬平台采集；Playwright CDP 做重反爬平台

---

## 三、整体架构

```
┌────────────────────────────────────────────────────────────────────────────┐
│                             前端层 (Next.js)                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────────┐   │
│  │ 寻源工作台  │  │ 任务管理    │  │ 候选人看板  │  │ 平台健康 + 账号管理 │   │
│  │ (创建任务)  │  │ (进度/日志) │  │ (多源聚合)  │  │ (状态/配置)        │   │
│  └────────────┘  └────────────┘  └────────────┘  └────────────────────┘   │
└─────────────────────────────┬──────────────────────────────────────────────┘
                              │ REST API + WebSocket
┌─────────────────────────────▼──────────────────────────────────────────────┐
│                         后端 API 层 (FastAPI)                                │
│  Existing: /api/v1/candidates /jobs /applications /auth /...               │
│  NEW: /api/v1/sourcing/*                                                    │
└─────────────────────────────┬──────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────────────────┐
│                        P0-P2: 扁平执行层 (无 Agent)                           │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  sourcing/orchestrator.py          — 任务编排（唯一入口）            │    │
│  │  sourcing/platforms/base.py        — PlatformAdapter 基类           │    │
│  │  sourcing/platforms/boss_zhipin.py — Playwright CDP 实现            │    │
│  │  sourcing/platforms/liepin.py      — Scrapling HTTP 实现            │    │
│  │  sourcing/platforms/github.py      — Scrapling HTTP 实现            │    │
│  │  sourcing/dedup.py                 — 指纹去重                        │    │
│  │  sourcing/account_manager.py       — 账号 + Cookie 管理             │    │
│  │  sourcing/proxy_pool.py            — 代理池                         │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│                        P4+: 引入 Agent 层                                    │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  sourcing/agents/analyze_agent.py   — LLM 分析                      │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────┬──────────────────────────────────────────────┘
                              │ arq worker (Redis-backed async queue)
┌─────────────────────────────▼──────────────────────────────────────────────┐
│                         执行层 (Execution)                                    │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐    │
│  │ Scrapling HTTP     │  │ Playwright CDP     │  │ Scrapling Spider   │    │
│  │ (低反爬平台)        │  │ (高反爬平台: BOSS)  │  │ (并发批量场景)      │    │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘    │
└─────────────────────────────┬──────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────────────────┐
│                      基础设施 (已有)                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │PostgreSQL│  │ Redis    │  │ Qdrant   │  │ MinIO   │  │ Prometheus+  │ │
│  │(主数据)   │  │(队列/缓存)│  │(向量)    │  │(文件)    │  │ Grafana      │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**关键简化**：P0-P2 不新建 agents/ 子模块。orchestrator.py 充当 Agent 角色，等 P4 AI 分析阶段再创建 SourcingAnalyzeAgent。

---

## 四、模块结构

### 4.1 后端模块（P0-P2 扁平结构）

```
apps/api/app/sourcing/
├── __init__.py
├── config.py                     # 寻源配置 (Pydantic Settings)
│
├── models/                       # SQLAlchemy 模型
│   ├── __init__.py
│   ├── sourcing_task.py           # 采集任务
│   ├── crawl_log.py               # 采集日志
│   ├── platform_config.py         # 平台配置
│   └── platform_account.py        # 平台账号 (NEW: 账号管理)
│
├── schemas/                      # Pydantic DTO
│   ├── __init__.py
│   ├── task.py
│   ├── candidate.py
│   ├── platform.py
│   └── stats.py
│
├── api/                          # API 路由
│   ├── __init__.py
│   ├── tasks.py                  # /api/v1/sourcing/tasks
│   ├── platforms.py              # /api/v1/sourcing/platforms
│   ├── candidates.py             # /api/v1/sourcing/candidates
│   └── stats.py                  # /api/v1/sourcing/stats
│
├── orchestrator.py               # ⭐ 任务编排（核心，替代 agents/ + services/ + tasks/）
│
├── platforms/                    # 平台适配器
│   ├── __init__.py               #   pkgutil 自动注册
│   ├── base.py                   #   PlatformAdapter 抽象基类
│   ├── boss_zhipin.py            #   BOSS直聘 (Playwright CDP)
│   ├── liepin.py                 #   猎聘 (Scrapling HTTP)
│   ├── maimai.py                 #   脉脉 (Scrapling HTTP)
│   ├── linkedin.py               #   LinkedIn (Scrapling HTTP)
│   └── github.py                 #   GitHub (API)
│
├── dedup.py                      # 去重引擎（指纹 + 模糊匹配）
├── account_manager.py            # 账号管理（Cookie 持久化/配额/封号检测）
├── proxy_pool.py                 # 代理池
│
└── arq_worker.py                 # arq 队列 worker
```

### 4.2 前端模块

```
apps/web/app/sourcing/
├── page.tsx                      # 工作台首页
├── layout.tsx
│
├── tasks/
│   ├── page.tsx                  # 任务列表（P2a: 轮询）
│   └── [taskId]/
│       └── page.tsx              # 任务详情（P2a: 轮询 / P2b: WebSocket 实时）
│
├── candidates/
│   ├── page.tsx                  # 候选人列表
│   └── [candidateId]/
│       └── page.tsx              # 多源聚合详情
│
└── platforms/
    └── page.tsx                  # 平台 + 账号配置
```

---

## 五、数据模型

### 5.1 设计原则

- Candidate 表**直接加新字段**（全 `nullable=True` 无损兼容）
- 所有 sourcing 新表用独立前缀 `sourcing_`
- 统一 ULID 主键

### 5.2 SourcingTask — 采集任务

```python
class SourcingTaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"       # 部分平台成功
    FAILED = "failed"
    CANCELLED = "cancelled"

class SourcingTask(Base):
    __tablename__ = "sourcing_tasks"

    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=ulid)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)

    # 任务参数
    keyword: Mapped[str] = mapped_column(String(500), nullable=False, comment="搜索关键词")
    platforms: Mapped[list] = mapped_column(ARRAY(String), comment="目标平台列表")
    filters: Mapped[dict] = mapped_column(JSON, default=dict, comment="筛选条件: 城市/薪资/年限等")

    # 执行状态
    status: Mapped[SourcingTaskStatus] = mapped_column(
        SAEnum(SourcingTaskStatus, values_callable=lambda x: [e.value for e in x]),
        default=SourcingTaskStatus.PENDING, index=True,
    )
    progress: Mapped[dict] = mapped_column(JSON, default=dict, comment="各平台进度快照")
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    after_dedup: Mapped[int] = mapped_column(Integer, default=0)
    new_this_run: Mapped[int] = mapped_column(Integer, default=0, comment="本批新增(去重后)")

    # 调度
    priority: Mapped[int] = mapped_column(Integer, default=50, comment="优先级 0-100")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # 审计
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关联
    logs = relationship("CrawlLog", back_populates="task", lazy="dynamic")
```

### 5.3 CrawlLog — 采集日志

```python
class CrawlStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BANNED = "banned"           # IP 被封
    ACCOUNT_BANNED = "account_banned"  # NEW: 账号被封
    CAPTCHA = "captcha"         # 触发验证码
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"     # NEW: 被限频
    QUOTA_EXCEEDED = "quota_exceeded" # NEW: 账号日配额用完
    SKIPPED = "skipped"

class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=ulid)
    task_id: Mapped[str] = mapped_column(ForeignKey("sourcing_tasks.id"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, comment="平台标识")
    url: Mapped[str] = mapped_column(Text, nullable=True, comment="目标 URL")
    page: Mapped[int] = mapped_column(Integer, default=1, comment="页码")

    status: Mapped[CrawlStatus] = mapped_column(
        SAEnum(CrawlStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    proxy_used: Mapped[str] = mapped_column(String(100), nullable=True, comment="使用的代理")
    account_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True, comment="关联平台账号")
    captcha_solved: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="重试次数")

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # 关联
    task = relationship("SourcingTask", back_populates="logs")
```

### 5.4 Candidate 扩展字段

```python
# 在 apps/api/app/models/candidate.py 新增字段
class Candidate(Base):
    __tablename__ = "candidates"

    # ... 现有字段保持不动 ...

    # === NEW: 寻源扩展 (全 nullable, 无损兼容) ===
    sourcing_task_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="来源采集任务ID"
    )
    source_platforms: Mapped[list | None] = mapped_column(
        ARRAY(String), nullable=True, comment="来源平台列表"
    )
    source_urls: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="各平台 URL {boss_zhipin: url, ...}"
    )
    raw_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="各平台原始解析数据 {boss_zhipin: {...}}"
    )
    ai_analysis: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="AI 分析结果缓存"
    )
    match_scores: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="按岗位匹配分 {job_id: score}"
    )
    data_quality_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="数据质量评分 0-1"
    )
    dedup_fingerprint: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="去重指纹"
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="上次采集时间"
    )
```

### 5.5 PlatformConfig — 平台配置

```python
class PlatformConfig(Base):
    __tablename__ = "sourcing_platform_configs"

    name: Mapped[str] = mapped_column(String(50), primary_key=True, comment="平台标识")
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, comment="job_board/social/code/academic")
    anti_crawl_level: Mapped[int] = mapped_column(Integer, default=3, comment="1-5")
    requires_login: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit: Mapped[int] = mapped_column(Integer, default=3, comment="请求间隔(秒)")
    daily_quota_per_account: Mapped[int] = mapped_column(Integer, default=300, comment="每账号日配额")

    config: Mapped[dict] = mapped_column(JSON, default=dict, comment="平台特有配置")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")
    health_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

### 5.6 PlatformAccount — 平台账号（**新增**）

```python
class PlatformAccount(Base):
    """平台账号管理"""
    __tablename__ = "sourcing_platform_accounts"

    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=ulid)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="账号标识")
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="crawl",
        comment="primary(主号)/backup(备用)/crawl(采集号)"
    )

    # 凭证（加密存储）
    encrypted_cookies: Mapped[str | None] = mapped_column(Text, nullable=True, comment="AES 加密 Cookie")
    cookie_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 健康状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active",
        comment="active/banned/limited/expired"
    )
    daily_used: Mapped[int] = mapped_column(Integer, default=0, comment="今日已用配额")
    quota_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="配额重置时间"
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, comment="连续失败次数")
    last_banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

### 5.7 表关系总图

```
sourcing_tasks
    │
    ├── 1:N ── crawl_logs
    │              │
    │              └── N:1 ── sourcing_platform_accounts (通过 account_id)
    │
    └── 1:N ── candidates (通过 sourcing_task_id)
                     │
                     └── 与现有 Application / Interview / Evaluation 等关系不变

sourcing_platform_configs (独立配置表)
sourcing_platform_accounts (独立账号表)
```

---

## 六、去重策略

### 6.1 指纹生成算法

```
指纹 = SHA256(归一化姓名 + "|" + 归一化公司 + "|" + 标准化职位)

其中:
  归一化姓名 = 去空格 + 全角转半角 + 小写
  归一化公司 = NLP 公司名归一化 (去除"北京""有限公司""科技"等后缀)
  标准化职位 = 提取核心职位词 (如 "Python工程师" → "python")
```

### 6.2 精确去重（P0-P2）

```python
import hashlib
import re

def normalize_name(name: str) -> str:
    """归一化姓名"""
    name = name.replace(" ", "").replace("\u3000", "")  # 去空格
    name = name.replace("·", "").replace("•", "")        # 去中间点
    return name.lower()

def normalize_company(company: str) -> str:
    """公司名归一化（规则版，P4 升级 NLP）"""
    company = re.sub(r'(北京|上海|广州|深圳|杭州|成都)', '', company)
    company = re.sub(r'(有限公司|股份有限公司|集团|科技|技术|有限)', '', company)
    company = company.strip()
    return company.lower()

def generate_fingerprint(name: str, company: str, title: str) -> str:
    n_name = normalize_name(name)
    n_company = normalize_company(company)
    n_title = title.strip().lower()[:20]  # 截断避免噪声
    raw = f"{n_name}|{n_company}|{n_title}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

### 6.3 模糊匹配（P3+）

指纹匹配捕获相同候选人，但以下情况需要模糊匹配：
- 同人不同公司（简历更新了）
- 同人不同写法（"张 三" vs "张三"）
- 姓名中间名省略

```python
def fuzzy_dedup(new_candidate: dict, existing_fingerprints: list[str]) -> bool:
    """
    模糊匹配: 姓名 Levenshtein + 公司 Jaccard
    只有当 姓名相似度 > 0.85 且 公司无关时标记为"可能同人"
    """
    from rapidfuzz import fuzz  # 或 python-Levenshtein
    name = normalize_name(new_candidate["name"])
    for fp in existing_fingerprints:
        # 解码指纹
        parts = fp.split("|")
        if len(parts) >= 1 and fuzz.ratio(name, parts[0]) > 85:
            return True  # 疑似重复
    return False
```

### 6.4 增量采集

```python
def is_already_crawled(dedup_fingerprint: str, platform: str) -> bool:
    """
    采集前检查：此指纹 + 此平台是否已采集过
    实现：Redis Set SISMEMBER sourcing:dedup:{platform} {fingerprint}
    """
    ...

def mark_crawled(dedup_fingerprint: str, platform: str):
    """采集后标记"""
    redis.sadd(f"sourcing:dedup:{platform}", dedup_fingerprint)
    redis.expire(f"sourcing:dedup:{platform}", 86400 * 30)  # 30天过期
```

每次新任务自动跳过已采候选人，只增量更新。

---

## 七、账号管理体系

### 7.1 账号等级

| 类型 | 用途 | 日配额 | 封号风险 |
|------|------|--------|---------|
| **主号** (primary) | 人工日常使用 | 正常 | 最低 |
| **备用号** (backup) | 主号受限时降级使用 | 正常 | 低 |
| **采集号** (crawl) | 高频采集 | 200-300/天 | 较高，可承受 |

### 7.2 Cookie 生命周期

```
登录成功
    │
    ▼
加密存 Redis (AES-256-GCM) ───→ 同时存 DB (sourcing_platform_accounts.encrypted_cookies)
    │
    ├── 每次请求前：检查 Cookie 是否过期
    ├── 过期 → 尝试刷新 Cookie
    │          ├── 刷新成功 → 更新存储
    │          └── 刷新失败 → 标记账号 expired，切下一个账号
    │
    ├── 请求返回 302 到登录页 → 标记 Cookie 失效
    └── 连续 10 次 failed → 标记账号 banned，触发告警
```

### 7.3 配额管理

```python
class AccountManager:
    async def acquire(self, platform: str) -> PlatformAccount | None:
        """获取一个可用账号（按优先级: primary > backup > crawl）"""
        accounts = await self._get_active_accounts(platform)
        for account in accounts:
            if account.daily_used < await self._get_daily_quota(platform):
                return account
        return None  # 所有账号配额用完

    async def report_usage(self, account_id: str, count: int = 1):
        """报告采集用量"""
        account = await self._get_account(account_id)
        account.daily_used += count
        # 如果超过配额 90%，标记为 quota_exceeded
        quota = await self._get_daily_quota(account.platform)
        if account.daily_used >= quota * 0.9:
            account.status = "limited"
        await self._save_account(account)

    async def rotate(self, platform: str, failed_account_id: str) -> PlatformAccount | None:
        """失败时自动轮换到下一个账号"""
        await self._mark_failure(failed_account_id)
        return await self.acquire(platform)
```

### 7.4 账号预热策略

新注册账号不能马上高频采集，需要"养号"：
- Day 1-3：每天浏览 5-10 个岗位，不搜索
- Day 4-7：每天搜索 2-3 次，每次看 5 人
- Day 8-14：逐步增加频率到正常采集的 30%
- Day 15+：正常使用

**P0-P2 实现**：先人工登录导 Cookie，不做自动预热。P3+ 再实现自动化。

---

## 八、反爬对抗（现实主义版）

### BOSS直聘反爬真实情况

```
BOSS直聘反爬等级 4/5，主要手段：

L1 IP 检测层
   ├── 数据中心 IP 几乎全封
   ├── 部分住宅 IP 也被标记
   └── 需要高质量住宅代理 (¥3-5/GB)

L2 设备指纹层
   ├── Canvas/WebGL/AudioContext 指纹
   ├── 屏幕分辨率/字体列表/时区
   └── TLS 握手指纹 (JA3)

L3 行为分析层
   ├── 鼠标轨迹 / 滚动模式 / 点击间隔
   ├── 页面停留时间过短 (< 2s) → 标记
   └── 访问路径不符合正常用户模式

L4 账号行为层
   ├── 日查看简历数超过 300 → 限流
   ├── 短时间内搜索大量不同关键词 → 风控
   ├── 从同一个 IP 登录多个账号 → 封
   └── 新号高频操作 → 触发人工审核

L5 验证码层
   ├── 滑块验证码 (极验/行为验)
   ├── 点选验证码 (触发的少)
   └── 偶尔弹手机验证
```

### 应对策略

```
┌──────────────────────────────────────────────────────────────────┐
│                    反爬策略矩阵                                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  L1 IP 层                                                       │
│  ├── 只使用住宅代理 (数据中心的 IP 直接放弃，测都不用测)          │
│  ├── 代理池最少 20 个 IP，轮换使用                               │
│  └── 单 IP 每 10 分钟不超过 30 次请求                            │
│                                                                  │
│  L2 指纹层                                                       │
│  ├── Playwright CDP 模式 ≈ 真实浏览器指纹 (比 HTTP 强得多)        │
│  ├── 每个 browser context 用独立 fingerprint                     │
│  └── 启动参数: --disable-blink-features=AutomationControlled     │
│                                                                  │
│  L3 行为层                                                       │
│  ├── 使用 Playwright 模拟真实鼠标轨迹 (page.mouse.move + human)  │
│  ├── 随机停留时间: 3-8 秒/页, 15-30 秒/详情                     │
│  ├── 滚动行为: 分 3-5 段滚到底，不是一次性                       │
│  └── 模拟"阅读"行为: 偶尔悬停、选中文字                          │
│                                                                  │
│  L4 账号层 → 见第七章                                             │
│                                                                  │
│  L5 验证码层                                                     │
│  ├── 滑块验证码: Playwright CDP + 人工打码 (2Captcha)            │
│  └── 触发率超过 20% → 暂停采集，切换代理/账号                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 各平台反爬等级与应对

| 平台 | 反爬等级 | 应对策略 | 可用工具 |
|------|---------|---------|---------|
| **BOSS直聘** | 4/5 | Playwright CDP + 住宅代理 + 账号管理 | CDP Chrome |
| **猎聘** | 3/5 | Scrapling StealthyFetcher + 住宅代理 | Scrapling HTTP |
| **脉脉** | 3/5 | Scrapling StealthyFetcher + 住宅代理 | Scrapling HTTP |
| **LinkedIn** | 2/5 | Scrapling FetcherSession (公开 API) | Scrapling HTTP |
| **GitHub** | 1/5 | GitHub API Token | HTTP API |
| **知乎** | 2/5 | Scrapling FetcherSession | Scrapling HTTP |

### ProxyPool 设计

```python
class ProxyPool:
    """三层代理池"""

    TIERS = {
        "premium":   {"type": "residential_china", "cost": "¥3-5/GB", "supplier": "BrightData/9Proxy"},
        "standard":  {"type": "residential_global", "cost": "¥0.8/GB", "supplier": "BrightData"},
        "mobile":    {"type": "mobile", "cost": "¥8/GB", "supplier": "BrightData"},
    }

    async def get_proxy(self, platform: str, anti_crawl_level: int) -> str:
        """按平台反爬等级返回对应 tier 的代理"""
        if platform == "boss_zhipin":
            return await self._acquire("premium")     # BOSS直聘必须住宅代理
        elif anti_crawl_level >= 3:
            return await self._acquire("standard")
        elif anti_crawl_level >= 1:
            return await self._acquire("mobile")
        return None  # GitHub 直连

    async def report_failure(self, proxy: str, platform: str, error_type: str):
        """报告代理失败, 自动降级, 阈值内剔除"""
        ...
```

---

## 九、错误分类与恢复

### 9.1 错误类型与恢复策略

| 错误类型 | 触发条件 | 立即处理 | 恢复策略 |
|---------|---------|---------|---------|
| `IP_BANNED` | HTTP 403/429 + "IP受限" | 标记此 IP 不可用 | 切换代理，15分钟后重试 |
| `ACCOUNT_BANNED` | 登录页跳转/封号提示 | 标记账号 banned | 切换账号，通知人工 |
| `CAPTCHA` | 检测到验证码元素 | 尝试打码 | 打码成功继续，失败切换代理 |
| `RATE_LIMITED` | HTTP 429/响应慢 | 增加间隔 | 指数退避 2^n * 60s |
| `QUOTA_EXCEEDED` | 账号日配额用完 | 标记账号 limited | 切下一账号，第二天自动恢复 |
| `TIMEOUT` | 超时 30s+ | 重试 3 次 | 3次都超时 → 切换代理+账号 |
| `PARSE_ERROR` | 关键字段缺失 > 30% | 标记失败，记录原始 HTML | 人工分析页面结构变更 |

### 9.2 恢复执行器

```python
class RecoveryExecutor:
    """带恢复逻辑的采集执行器"""

    MAX_RETRIES = 3
    ERROR_ESCALATION = {
        CrawlStatus.BANNED: "switch_proxy",
        CrawlStatus.ACCOUNT_BANNED: "switch_account",
        CrawlStatus.CAPTCHA: "attempt_solve",
        CrawlStatus.RATE_LIMITED: "backoff",
        CrawlStatus.QUOTA_EXCEEDED: "switch_account",
        CrawlStatus.TIMEOUT: "retry",
    }

    async def execute_with_recovery(
        self,
        platform: str,
        keyword: str,
        filters: dict,
    ) -> CrawlResult:
        """带多层恢复的采集执行"""
        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                adapter = self._get_adapter(platform)
                result = await adapter.search(keyword, **filters)
                if result.success:
                    return result
                # 非成功但没抛异常 → 按状态处理
                recovery = self.ERROR_ESCALATION.get(result.status)
                if recovery == "switch_proxy":
                    await self.proxy_pool.report_failure(...)
                elif recovery == "switch_account":
                    await self.account_manager.rotate(platform, ...)
                elif recovery == "backoff":
                    await asyncio.sleep(2 ** attempt * 60 + random.randint(0, 30))
                continue  # 重试
            except Exception as e:
                last_error = e
                await asyncio.sleep(2 ** attempt * 10)
        return CrawlResult(success=False, error_message=str(last_error))
```

---

## 十、增量采集策略

### 10.1 为什么需要增量

同关键词第二次跑时，如果全量重爬：
- 浪费代理费（每次都要请求）
- 浪费配额（每个账号每天只有 300 人）
- 增加封号风险（高频次 = 高风控）

### 10.2 增量实现

```python
class IncrementalCrawler:
    """增量采集器"""

    async def should_crawl(self, fingerprint: str, platform: str) -> bool:
        """检查是否已采集过"""
        key = f"sourcing:dedup:{platform}"
        return not await redis.sismember(key, fingerprint)

    async def mark_crawled(self, fingerprint: str, platform: str, ttl_days: int = 30):
        key = f"sourcing:dedup:{platform}"
        await redis.sadd(key, fingerprint)
        await redis.expire(key, 86400 * ttl_days)

    async def needs_refresh(self, candidate_id: str, max_age_days: int = 7) -> bool:
        """检查候选人是否需要刷新（7天前的数据）"""
        candidate = await candidate_service.get(candidate_id)
        if not candidate.last_crawled_at:
            return True
        age = datetime.utcnow() - candidate.last_crawled_at
        return age.days > max_age_days
```

### 10.3 采集流程

```
创建任务
    │
    ▼
对每个平台:
  ├── 搜索关键词，获取结果列表（第1页-第N页）
  ├── 对每个候选人:
  │     ├── 生成 fingerprint
  │     ├── Redis SISMEMBER 检查是否已采
  │     ├── 已采 → 跳过（可选: 7天前的才刷新）
  │     └── 未采 → 请求详情页 → 解析 → 检查必要字段 → 存储
  │
  └── 单平台完成后:
        ├── 更新 task.progress
        └── 释放账号配额

所有平台完成后:
  ├── 去重（精确 + 模糊）
  ├── 更新 sourcing_task 状态
  └── 如果配置了 → 触发 AI 分析
```

---

## 十一、异步任务体系

### 11.1 为什么不用 asyncio.create_task

```
v3 方案: asyncio.create_task 在 FastAPI 中调度
问题:
  1. 进程重启 → 所有 in-flight 任务丢失
  2. 无重试机制
  3. 无任务状态持久化
  4. 多 worker 时重复执行

v4 方案: arq (Redis-backed async queue)
  优势:
  1. 任务持久化到 Redis，重启不丢失
  2. 内置重试 + backoff
  3. 支持并发控制
  4. 轻量，单文件启动
  5. 异步原生（和 FastAPI 一样 async）
```

### 11.2 arq 集成

```python
# apps/api/app/sourcing/arq_worker.py
from arq import create_pool, cron
from arq.connections import RedisSettings

# arq worker 启动: arq app.sourcing.arq_worker.WorkerSettings

async def crawl_task(ctx, task_id: str):
    """采集任务 - arq 保证持久化"""
    orchestrator = ctx["orchestrator"]
    task = await orchestrator.get_task(task_id)
    if not task or task.status != "pending":
        return {"skipped": True}
    await orchestrator.execute_task(task)

async def analyze_candidates(ctx, candidate_ids: list[str], jd_id: str | None):
    """AI 分析任务"""
    ...

class WorkerSettings:
    functions = [crawl_task, analyze_candidates]
    redis_settings = RedisSettings(host="localhost", port=6379, database=1)
    keep_result = 86400          # 结果保存1天
    keep_result_failed = 86400   # 失败结果也保存
    max_tries = 3                # 最大重试3次
    max_retry_delay = 300        # 最长重试间隔5分钟
    job_timeout = 3600           # 最长执行1小时
    concurrency = 2              # 并发2个 worker
```

### 11.3 API → Worker 调用

```python
# apps/api/app/sourcing/orchestrator.py
from arq import create_pool

class SourcingOrchestrator:
    """任务编排 - P0-P2 唯一入口"""

    def __init__(self, db, redis, proxy_pool, account_manager):
        self.db = db
        self.redis = redis
        self.proxy_pool = proxy_pool
        self.account_manager = account_manager

    async def create_and_dispatch(self, task_data: dict) -> SourcingTask:
        """创建任务 + 推入队列"""
        task = SourcingTask(**task_data)
        self.db.add(task)
        await self.db.commit()

        # 推入 arq 队列
        pool = await create_pool(RedisSettings())
        await pool.enqueue_job("crawl_task", task.id)
        return task

    async def cancel_task(self, task_id: str):
        """取消任务"""
        pool = await create_pool(RedisSettings())
        await pool.cancel_job(task_id)  # 实际需要更复杂的取消逻辑
```

---

## 十二、API 设计

### 12.1 端点列表

```
# 任务管理
GET    /api/v1/sourcing/tasks                       → 任务列表 (分页+筛选+排序)
POST   /api/v1/sourcing/tasks                       → 创建采集任务
GET    /api/v1/sourcing/tasks/{id}                  → 任务详情+进度
DELETE /api/v1/sourcing/tasks/{id}                  → 取消任务
GET    /api/v1/sourcing/tasks/{id}/logs             → 任务采集日志

# 平台管理
GET    /api/v1/sourcing/platforms                   → 平台列表+健康状态
PUT    /api/v1/sourcing/platforms/{name}            → 更新平台配置
POST   /api/v1/sourcing/platforms/{name}/health-check → 手动健康检查

# 平台账号管理
GET    /api/v1/sourcing/platforms/{name}/accounts   → 平台账号列表
POST   /api/v1/sourcing/platforms/{name}/accounts   → 添加账号
DELETE /api/v1/sourcing/platforms/{name}/accounts/{id} → 删除账号
POST   /api/v1/sourcing/platforms/{name}/accounts/{id}/renew-cookie → 更新 Cookie

# 寻源候选人
GET    /api/v1/sourcing/candidates                  → 寻源候选人列表
GET    /api/v1/sourcing/candidates/{id}             → 候选人多源聚合详情
POST   /api/v1/sourcing/candidates/{id}/analyze     → 触发 AI 分析
POST   /api/v1/sourcing/candidates/{id}/merge       → 手动合并多源

# 统计
GET    /api/v1/sourcing/stats                       → 采集统计

# WebSocket 实时进度 (P2b+)
WS     /ws/sourcing/tasks/{id}                      → 任务实时进度推送
```

### 12.2 鉴权

- 复用现有 org-scoped RBAC
- `sourcing:task:create` / `sourcing:task:read` / `sourcing:task:cancel` 权限
- 平台配置仅 `admin` 角色可改
- 账号管理仅 `admin` 角色可操作

---

## 十三、前端设计

### 13.1 分期策略（修正版：拆 P2a / P2b）

| 子阶段 | 周期 | 交付物 | 技术方案 |
|--------|------|--------|---------|
| **P2a** | 1-2 周 | 任务创建/列表、候选人列表（只读）、平台状态 | 轮询，无 WebSocket，无实时 |
| **P2b** | 2 周 | WebSocket 实时进度、任务详情实时、候选人聚合详情 | WebSocket + TanStack Query |

### 13.2 页面组件树

```
sourcing/
├── layout.tsx                    # 布局 (Nav + Sidebar)
├── page.tsx                      # 工作台
│   ├── QuickCreateForm           # 快速创建任务表单
│   ├── RecentTasks               # 最近任务列表
│   └── PlatformStatusCards       # 各平台健康状态卡片
│
├── tasks/
│   ├── page.tsx                  # 任务列表 (P2a)
│   │   ├── TaskFilters           # 状态/平台/日期筛选
│   │   ├── TaskTable             # 任务数据表格
│   │   └── Pagination
│   │
│   └── [taskId]/
│       └── page.tsx              # 任务详情
│           ├── TaskHeader        # 标题/状态/操作按钮
│           ├── PlatformProgress  # 各平台进度条 (P2a: 轮询, P2b: WebSocket)
│           ├── CandidatePreview  # 已采集候选人预览表
│           └── CrawlLogPanel     # 采集日志
│
├── candidates/
│   ├── page.tsx                  # 候选人列表 (P2a)
│   │   ├── SearchFilters
│   │   ├── CandidateTable
│   │   └── BulkActions
│   │
│   └── [candidateId]/
│       └── page.tsx              # 多源聚合详情 (P2b)
│           ├── IdentityCard
│           ├── SourceTabs
│           ├── AIAnalysisPanel
│           └── Timeline
│
└── platforms/
    └── page.tsx                  # 平台+账号管理 (P2b)
        ├── PlatformTable
        ├── PlatformConfigModal
        └── AccountListModal      # 账号管理弹窗
```

### 13.3 数据流

```
P2a (轮询):
  API 请求 ─→ TanStack Query (每 5s 刷新) ─→ 组件渲染

P2b (实时):
  API 请求 ─→ TanStack Query ─→ Zustand (UI 状态)
  WebSocket ─→ Zustand taskStore ─→ 组件订阅
```

---

## 十四、隐私合规

### 14.1 数据采集边界

| 可采集 | 不可采集 |
|--------|---------|
| 姓名（公开简历） | 身份证号 |
| 工作经历 | 家庭住址 |
| 技能标签 | 银行账号 |
| 教育背景 | 社保信息 |
| 公开项目/作品 | 非公开联系方式 |

### 14.2 数据存储加密

```python
class Candidate(Base):
    # 手机号 AES-256-GCM 加密存储
    phone: Mapped[str | None] = mapped_column(
        String(512), nullable=True,  # 加密后长度增长
        comment="手机号 (AES-256-GCM 加密)"
    )
    # 邮箱 AES-256-GCM 加密存储
    email: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
        comment="邮箱 (AES-256-GCM 加密)"
    )

    @property
    def masked_phone(self) -> str | None:
        """脱敏显示: 138****1234"""
        if not self.phone:
            return None
        decrypted = decrypt(self.phone)  # 解密仅内部使用
        return decrypted[:3] + "****" + decrypted[-4:]

    @property
    def masked_email(self) -> str | None:
        """脱敏显示: j***@example.com"""
        if not self.email:
            return None
        decrypted = decrypt(self.email)
        return decrypted[0] + "***@" + decrypted.split("@")[1]
```

### 14.3 数据生命周期

| 策略 | 实现 |
|------|------|
| 自动清理 | 超过 180 天未更新的候选人自动归档到 `candidates_archive` 表 |
| 硬删除 | `DELETE /api/v1/sourcing/candidates/{id}` 触发物理删除 + 审计日志 |
| 数据主体删除 | `POST /api/v1/sourcing/candidates/{id}/gdpr-delete` 全链路删除（+关联日志匿名化） |
| 审计日志 | 所有采集/查看/导出操作记录 `audit_logs` 表 |

### 14.4 平台合规注意事项

- ✅ 遵守《个人信息保护法》(PIPL)
- ✅ 只采集公开信息（不绕过登录墙/付费墙）
- ✅ 控制采集频率：单平台每分钟不超过 20 次请求
- ⚠️ 使用境外代理时注意数据跨境传输限制
- ⚠️ 住宅代理采购需选择合规供应商（BrightData/9Proxy 有中国节点合规声明）
- ⚠️ 建议有法务审核后上线

---

## 十五、测试策略

### 15.1 层级

| 层级 | 工具 | 覆盖内容 | 目标 |
|------|------|---------|------|
| **Unit** | pytest + pytest-asyncio | 解析逻辑、去重算法、指纹生成 | 90%+ |
| **Mock** | pytest + respx | 模拟 HTTP 响应的解析测试 | 不依赖外部 |
| **Integration** | pytest + Testcontainers | DB 读写、arq 任务 | 真实 DB + Redis |
| **Health Check** | Playwright + 定时任务 | 真实浏览器探测平台是否可访问 | 每周自动跑 |
| **E2E** | Playwright | 真实登录 BOSS直聘 (用测试账号) | 冒烟，手动触发 |

### 15.2 关键测试用例

```python
# tests/unit/sourcing/test_dedup.py
class TestDedup:
    def test_exact_match(self):
        """精确指纹匹配"""
        fp1 = generate_fingerprint("张三", "字节跳动", "Python工程师")
        fp2 = generate_fingerprint("张三", "字节跳动", "Python工程师")
        assert fp1 == fp2

    def test_normalize_name_spaces(self):
        """全角/半角空格归一化"""
        fp1 = generate_fingerprint("张三", "字节跳动", "Python工程师")
        fp2 = generate_fingerprint("张 三", "字节跳动", "Python工程师")
        assert fp1 == fp2  # 去空格后相等

    def test_different_person_same_name(self):
        """同名不同人 → 不应匹配"""
        fp1 = generate_fingerprint("张三", "字节跳动", "Python工程师")
        fp2 = generate_fingerprint("张三", "阿里巴巴", "Java工程师")
        assert fp1 != fp2  # 不同公司+职位，不同人

    def test_normalize_company(self):
        """公司名归一化"""
        fp1 = generate_fingerprint("张三", "北京字节跳动科技有限公司", "Python工程师")
        fp2 = generate_fingerprint("张三", "字节跳动", "Python工程师")
        assert fp1 == fp2  # 归一化后相同


# tests/unit/sourcing/test_parse.py
class TestBossZhipinParse:
    """使用 Scrapling 解析器 + 本地 HTML fixture"""

    def test_parse_list_page_standard(self, boss_list_html_fixture):
        adapter = BossZhipinAdapter(config={}, proxy_pool=MagicMock())
        result = adapter.parse_list(boss_list_html_fixture)
        assert len(result) > 0
        assert result[0]["name"] is not None

    def test_parse_list_missing_fields(self, boss_list_partial_html_fixture):
        """字段缺失时不应抛异常"""
        adapter = BossZhipinAdapter(config={}, proxy_pool=MagicMock())
        result = adapter.parse_list(boss_list_partial_html_fixture)
        assert len(result) > 0
        # 缺失字段应为 None，不抛 KeyError


# tests/integration/test_arq_queue.py
class TestArqQueue:
    """arq 任务队列集成测试"""

    async def test_task_persistence(self, redis_client):
        """arq 任务在 Redis 中持久化"""
        pool = await create_pool(RedisSettings())
        job = await pool.enqueue_job("crawl_task", "test-task-id")
        assert job.job_id is not None
        info = await pool.get_job_info(job.job_id)
        assert info is not None
        assert info.function == "crawl_task"
```

### 15.3 平台健康探测（定时任务）

```python
# 每周自动执行: 探测各平台是否可访问
async def platform_health_check():
    """遍历所有 enabled 平台，执行一次轻量搜索"""
    for platform in enabled_platforms:
        adapter_cls = get_adapter(platform)
        adapter = adapter_cls(config={}, proxy_pool=proxy_pool)
        try:
            result = await adapter.search("test", limit=1)
            await update_health_status(platform, "healthy" if result.success else "degraded")
        except Exception:
            await update_health_status(platform, "down")
```

---

## 十六、可观测性

### 16.1 关键指标

| 指标 | 类型 | 告警阈值 | 说明 |
|------|------|---------|------|
| `sourcing_crawl_total` | Counter | - | 总采集请求数 |
| `sourcing_crawl_success_rate` | Gauge | < 60% 告警 | 成功率（滑动窗口 1h） |
| `sourcing_crawl_duration_seconds` | Histogram | p99 > 30s | 采集延迟 |
| `sourcing_account_active` | Gauge | < 2 告警 | 可用账号数 |
| `sourcing_proxy_pool_size` | Gauge | < 5 告警 | 可用代理数 |
| `sourcing_captcha_rate` | Gauge | > 20% 告警 | 验证码触发率 |
| `sourcing_daily_quota_used` | Gauge | > 80% 告警 | 账号配额使用率 |
| `sourcing_task_queue_depth` | Gauge | > 20 告警 | 排队任务数 |

### 16.2 Metric 埋点

```python
# 在 orchestrator.py 中埋点
from prometheus_client import Counter, Histogram, Gauge

crawl_total = Counter("sourcing_crawl_total", "Total crawl requests", ["platform", "status"])
crawl_duration = Histogram("sourcing_crawl_duration_seconds", "Crawl duration", ["platform"])
proxy_pool_size = Gauge("sourcing_proxy_pool_size", "Available proxies", ["tier"])
active_accounts = Gauge("sourcing_account_active", "Active accounts", ["platform", "status"])

async def execute_task(self, task: SourcingTask):
    for platform in task.platforms:
        with crawl_duration.labels(platform=platform).time():
            result = await self._crawl_platform(platform, task)
        status = "success" if result.success else "failed"
        crawl_total.labels(platform=platform, status=status).inc()
```

### 16.3 健康检查端点

```
GET /api/v1/sourcing/health
→ {
    "platforms": {
      "boss_zhipin": {"status": "healthy", "last_check": "...", "latency_ms": 1234},
      "liepin": {"status": "degraded", "last_check": "...", "error": "代理不可用"},
    },
    "accounts": {
      "boss_zhipin": {"active": 2, "total": 3, "quota_used_pct": 45},
    },
    "proxy_pool": {"premium": 15, "standard": 30, "mobile": 5},
    "queue_depth": 3,
  }
```

---

## 十七、实施路线图

### P0: 骨架 (1周)

```
目标: 项目结构 + 基础模型 + arq worker 跑通

交付物:
  □ apps/api/app/sourcing/ 目录创建
  □ 所有 Model + Alembic migration
  □ PlatformAdapter 基类 + 自动注册
  □ arq worker 集成，空任务可排队/执行
  □ PlatformConfig 种子数据（BOSS直聘/猎聘等）
  □ API 空路由（返回 501 Not Implemented）
  □ Scrapling 依赖安装

里程碑: 可创建 souring_task → arq 消费 → 状态更新（虽然采集还没实现）
```

### P1: BOSS直聘单平台 (4-6周)

```
目标: BOSS直聘采集跑通（有限可用）

交付物:
  □ BossZhipinAdapter — Playwright CDP 实现
    □ CDP Chrome 启动 + Cookie 注入
    □ 搜索关键词 + 翻页
    □ 候选人列表解析
    □ 候选人详情页解析
    □ 验证码检测 + 打码接入
  □ 代理池集成（住宅代理）
  □ AccountManager 基本版
    □ Cookie 持久化（Redis AES 加密）
    □ 配额跟踪
    □ 账号轮换
  □ 去重引擎 (精确指纹)
  □ 增量采集（Redis dedup set）
  □ 数据入库 → Candidate 表
  □ orchestrator.py 完整实现
  □ 错误恢复（重试 + 退避 + 代理切换）
  □ 日志系统（CrawlLog + 结构化日志）

里程碑: 输入关键词 → 自动采集 → 数据存到 DB → 可在 API 查看

风险:
  - BOSS直聘反爬策略变化（预留 2 周缓冲）
  - 住宅代理质量不稳定
  - Playwright CDP 在 CI 环境中不可用
```

### P2a: 基础前端 (1-2周)

```
目标: 可在 UI 创建任务 + 查看结果

交付物:
  □ 寻源工作台首页 (QuickCreateForm + RecentTasks)
  □ 任务列表页 (筛选/分页/排序)
  □ 任务详情页 (进度/日志/候选人预览) — 轮询
  □ 候选人列表页
  □ 前端 API 封装 (tRPC + TanStack Query)
  □ 权限集成 (sourcing:task:*)

里程碑: 前端全链路可用，可操作任务
```

### P2b: 前端增强 (2周)

```
目标: 实时体验 + 高级页面

交付物:
  □ WebSocket 实时进度推送 (任务详情页)
  □ 候选人多源聚合详情页
  □ 平台配置 + 账号管理页
  □ WebSocket 连接池 + Zustand store
  □ 错误/告警展示优化

里程碑: 完整 UX
```

### P3: 健壮性 (2-3周)

```
目标: 可连续运行 24h 不中断

交付物:
  □ 代理池 IP 质量评分 + 自动剔除
  □ 账号预热脚本
  □ 指数退避 + 抖动全面接入
  □ 平台健康探测（定时任务）
  □ Prometheus 指标 + Grafana 面板
  □ 告警规则（成功率/配额/代理池）
  □ 限频配置自动调整（基于响应头动态优化）
  □ 模糊去重 (rapidfuzz)

里程碑: 无人值守连续采集 24h 无异常
```

### P4: AI 分析 (2-3周)

```
目标: 候选人自动分析 + 匹配度评分

交付物:
  □ SourcingAnalyzeAgent
    □ 技能提取 + 标准化
    □ 职业轨迹分析
    □ 候选人摘要生成
  □ Qdrant 向量化（技能嵌入）
  □ JD 匹配度评分
  □ 置信度标记 (< 0.7 → "AI推测")
  □ 批量分析任务 (arq)

里程碑: 候选人自动带评分和摘要
```

### P5: 多平台 (4-6周)

```
目标: 覆盖 4+ 平台

交付物:
  □ 猎聘适配器 (Scrapling HTTP)
  □ 脉脉适配器 (Scrapling HTTP)
  □ LinkedIn 适配器 (Scrapling FetcherSession)
  □ GitHub 适配器 (API)
  □ 多源合并 UI（并排对比/差异标记）
  □ 平台特定反爬配置

里程碑: 输入一个关键词，从多平台聚合候选人
```

### P6: 工程化 (持续)

```
目标: 质量保障 + 运维自动化

交付物:
  □ 测试覆盖 > 80%
  □ CI/CD 流水线（含 Playwright 健康探测）
  □ 定时平台健康探测 → 告警通知
  □ 运维手册（故障处理流程）
  □ 数据归档策略（180天自动归档）
  □ 性能优化（慢查询/大 JSON 存储优化）

里程碑: CI 全绿
```

### 总依赖图

```
P0 (骨架, 1w) ──→ P1 (BOSS直聘, 4-6w) ──→ P2a (基础前端, 1-2w)
                                                  │
                                                  ├──→ P2b (前端增强, 2w)
                                                  │
                                                  └──→ P3 (健壮性, 2-3w)
                                                          │
                                                          └──→ P4 (AI分析, 2-3w)
                                                                  │
                                                                  └──→ P5 (多平台, 4-6w)
                                                                          │
                                                                          └──→ P6 (工程化, 持续)
```

**总工期**: 约 17-23 周（4-6 个月），比 v3 预估多了约 8 周，主要来自 P1 反爬预留缓冲和 P5 多平台内容细化。

---

## 十八、关键设计决策

### D1: 直接改 Candidate 表 vs 扩展表
**决策**: 直接改 Candidate 表加字段（全 nullable）
**理由**: 现有 Candidate 只有 63 行、14 个字段，全 nullable 无损兼容

### D2: Scrapling vs Playwright CDP
**决策**: Scrapling 做低反爬平台 HTTP 采集，Playwright CDP 做高反爬平台（BOSS直聘）。不引入 browser-use
**理由**: Scrapling HTTP 对 GitHub/猎聘足够；BOSS直聘需要 CDP + 真实账号，Playwright 直接控制比再套 browser-use 更可控

### D3: arq vs asyncio.create_task vs Celery
**决策**: P0+ 就用 **arq**（Redis 持久化队列）。不经过 asyncio.create_task
**理由**: create_task 丢失任务不可接受。arq 轻量、异步原生、Redis 持久化。非必要不升级 Celery

### D4: P0-P2 扁平架构 vs 分层架构
**决策**: P0-P2 只用 orchestrator.py 做编排，不创建 agents/ services/ tasks/ 三层
**理由**: 三层职责重叠（都是协调和执行），合并后更清晰。P4 AI 分析阶段再引入 Agent 层

### D5: 精确去重先上，模糊去重 P3+
**决策**: P0-P2 用 SHA256 指纹精确去重，P3+ 加 rapidfuzz 模糊匹配
**理由**: 精确去重覆盖 80% 场景，实现简单。模糊匹配需要 Levenshtein 索引，P3 引入不影响前序开发

### D6: 增量采集默认开启
**决策**: 所有采集任务自动检查 Redis dedup set，跳过已采候选人
**理由**: 省代理费、省配额、省时间。每周同关键词跑一次，只新增不重爬

### D7: 前端分两期（P2a/P2b）
**决策**: P2a 只做轮询版，P2b 才上 WebSocket
**理由**: WebSocket 复杂度高，不应阻塞其他工作。轮询版 1-2 周可交付，用户能用起来

### D8: BOSS直聘适配器用 Playwright CDP 直接实现
**决策**: 不套 Scrapling，不套 browser-use。Playwright `page` 对象直接操作
**理由**: BOSS直聘的交互是固定模式（登录→搜索→列表→详情→翻页），不需要 LLM 决策。直接 Playwright 比套任何框架都可靠

### D9: 不引入 Elasticsearch
**决策**: 候选人搜索复用 PostgreSQL 全文索引 + Qdrant 向量搜索
**理由**: 现有系统已有 Qdrant，增加 ES 带来运维成本。PostgreSQL 全文搜索对候选人搜索场景足够

### D10: 适配器插件化自动注册
**决策**: pkgutil 自动发现，新增平台=写一个文件
**理由**: 低心智负担，高可扩展性

---

## 十九、成本估算（修正版）

| 项目 | P0 | P1 (BOSS直聘) | P2a-P2b (前端) | P3 (健壮性) | P4 (AI) | P5-P6 (多平台+工程) |
|------|-----|--------------|---------------|-------------|---------|-------------------|
| **LLM API (分析)** | ¥0 | ¥0 | ¥0 | ¥0 | ¥200-500/月 | ¥500-1000/月 |
| **代理 (住宅)** | ¥100-200 | ¥500-1000/月 | ¥500-1000/月 | ¥500-1000/月 | ¥500-1000/月 | ¥800-1500/月 |
| **打码服务** | ¥0 | ¥0-100/月 | ¥0-100/月 | ¥0-100/月 | ¥0-100/月 | ¥100-300/月 |
| **服务器 (已有)** | ¥0 | ¥0 | ¥0 | ¥0 | ¥0 | ¥0 |
| **BrightData 代理** | ¥100 | ¥300-500/月 | ¥300-500/月 | ¥300-500/月 | ¥300-500/月 | ¥500-800/月 |
| **人工(开发)** | 1人周 | 4-6人周 | 3-4人周 | 2-3人周 | 2-3人周 | 4-6人周 |
| **合计(现金)** | **¥100-200** | **¥300-1100/月** | **¥300-1100/月** | **¥300-1100/月** | **¥500-1600/月** | **¥900-2800/月** |

**修正要点**:
- P0 就需要代理测试（不能直连 BOSS直聘）
- P1 加入打码服务预算
- 代理费按中国住宅代理 ¥3-5/GB 计算
- 按每天采集 300-500 候选人、每候选人 3-5 页面估算流量

---

## 二十、实施任务清单（Todos）

### P0: 骨架（1周）

```
P0-1 [HIGH] 创建 apps/api/app/sourcing/ 目录结构，含所有子模块空文件
P0-2 [HIGH] 实现 sourcing_task.py / crawl_log.py / platform_config.py / platform_account.py 四个 SQLAlchemy 模型
P0-3 [HIGH] 在 Candidate 模型加寻源扩展字段（全 nullable，含 dedup_fingerprint / last_crawled_at）
P0-4 [HIGH] 生成 Alembic migration（新增 4 表 + Candidate 改表）
P0-5 [HIGH] 实现 PlatformAdapter 抽象基类 + pkgutil 自动注册机制
P0-6 [HIGH] 实现 Pydantic schemas（task.py / candidate.py / platform.py / stats.py）
P0-7 [HIGH] 实现 arq 队列集成（arq_worker.py + WorkerSettings，空 crawl_task 函数）
P0-8 [HIGH] 实现 API 路由骨架（tasks.py / platforms.py / candidates.py / stats.py，返回 501）
P0-9 [HIGH] 实现 SourcingTask API（CRUD + 创建任务推入 arq 队列）
P0-10[MED]  创建 souring_platform_configs 种子数据（BOSS直聘/猎聘/脉脉/LinkedIn/GitHub）
P0-11[HIGH] 安装依赖（scrapling / arq / playwright / crypt / rapidfuzz / prometheus_client）
P0-12[MED]  实现 config.py（Pydantic Settings，sourcing 专属配置项）
```

✅ 里程碑：可创建 souring_task → arq 消费 → 状态更新

### P1: BOSS直聘单平台（4-6周）

```
P1-1 [HIGH] 实现 ProxyPool（三层代理池 + get_proxy + report_failure + 健康检查）
P1-2 [HIGH] 实现 AccountManager（acquire / report_usage / rotate / Cookie 持久化 AES 加解密）
P1-3 [HIGH] 实现 Playwright CDP 浏览器管理（launch / context / fingerprint / 关闭）
P1-4 [HIGH] 实现 BossZhipinAdapter.login（CDP Chrome + Cookie 注入 + 登录态校验）
P1-5 [HIGH] 实现 BossZhipinAdapter.search（搜索关键词 + 列表页解析 + 翻页）
P1-6 [HIGH] 实现 BossZhipinAdapter.get_detail（候选人详情页解析）
P1-7 [MED]  实现 BossZhipinAdapter 验证码检测 + 打码接入（2Captcha/CapSolver）
P1-8 [HIGH] 实现 dedup.py 精确指纹引擎（generate_fingerprint + is_already_crawled + mark_crawled）
P1-9 [HIGH] 实现 orchestrator.py 完整版（create_and_dispatch / execute_task / _crawl_platform / _save_results）
P1-10[HIGH] 实现 RecoveryExecutor（execute_with_recovery / 错误分类恢复 / 指数退避）
P1-11[HIGH] 实现增量采集逻辑（execute_task 内 Redis dedup set 检查 + 跳过）
P1-12[MED]  实现爬虫监控点埋入（Prometheus metrics：crawl_total / crawl_duration / proxy_pool_size / active_accounts）
P1-13[MED]  实现 /api/v1/sourcing/health 健康检查端点（平台/账号/代理池/队列深度）
P1-14[MED]  实现完整的 /api/v1/sourcing/tasks/{id}/logs 采集日志 API
```

✅ 里程碑：输入关键词 → 自动采集 → 数据存到 DB → 可在 API 查看

### P2a: 基础前端（1-2周）

```
P2a-1 [HIGH] 创建 apps/web/app/sourcing/ 前端目录结构 + layout
P2a-2 [HIGH] 实现寻源工作台首页（QuickCreateForm + RecentTasks + PlatformStatusCards）
P2a-3 [HIGH] 实现任务列表页（TaskFilters + TaskTable + Pagination，轮询 5s）
P2a-4 [HIGH] 实现任务详情页（TaskHeader + PlatformProgress + CandidatePreview + CrawlLogPanel，轮询）
P2a-5 [HIGH] 实现寻源候选人列表页（SearchFilters + CandidateTable + BulkActions）
P2a-6 [HIGH] 封装前端 API 客户端（TanStack Query hooks + tRPC sourcing router）
P2a-7 [MED]  集成权限（sourcing:task:create / read / cancel）
```

✅ 里程碑：前端全链路可用，可操作任务

### P2b: 前端增强（2周）

```
P2b-1 [MED]  后端实现 /ws/sourcing/tasks/{id} WebSocket 端点 + TaskProgress 推送
P2b-2 [MED]  前端实现 WebSocket 连接池 + Zustand taskStore
P2b-3 [MED]  任务详情页升级 WebSocket 实时（进度条 + 候选人即时出现）
P2b-4 [MED]  实现候选人多源聚合详情页（IdentityCard + SourceTabs + Timeline）
P2b-5 [MED]  实现平台配置 + 账号管理页（PlatformConfigModal + AccountListModal）
```

✅ 里程碑：完整 UX

### P3: 健壮性（2-3周）

```
P3-1 [MED]  代理池升级（IP 质量评分 + 自动剔除劣质代理 + 补充）
P3-2 [MED]  实现账号预热脚本（新注册账号逐步增加采集频率）
P3-3 [MED]  实现平台健康探测定时任务（scrapling + Playwright 每 30min 轻量探测）
P3-4 [MED]  搭建 Grafana 面板（成功率/延迟/代理池/账号配额/验证码触发率）
P3-5 [MED]  配置 Prometheus 告警规则（成功率<60%/可用账号<2/代理池<5/配额>80%）
P3-6 [MED]  实现模糊去重（rapidfuzz 姓名 Levenshtein + 公司 Jaccard 相似度）
P3-7 [LOW]  限频自动调整（根据 HTTP 响应头/错误率动态调整请求间隔）
```

✅ 里程碑：无人值守连续采集 24h 无异常

### P4: AI 分析（2-3周）

```
P4-1 [MED]  实现 SourcingAnalyzeAgent（技能提取/标准化 + 职业轨迹分析 + 候选人摘要生成）
P4-2 [MED]  候选人技能嵌入向量化 + Qdrant 存储
P4-3 [MED]  实现 JD 匹配度评分（LLM 多维度对比技能/经验/行业）
P4-4 [MED]  批量分析任务入 arq 队列（analyze_candidates），分析后自动写回 Candidate.ai_analysis
P4-5 [LOW]  置信度标记 + 前端展示（< 0.7 标注 AI推测，人工确认按钮）
```

✅ 里程碑：候选人自动带评分和摘要

### P5: 多平台（4-6周）

```
P5-1 [MED]  实现猎聘适配器（Scrapling FetcherSession + 列表页解析 + 详情页解析）
P5-2 [MED]  实现脉脉适配器（Scrapling StealthyFetcher + 登录态 Cookie）
P5-3 [MED]  实现 LinkedIn 适配器（Scrapling FetcherSession + 公开资料搜索）
P5-4 [MED]  实现 GitHub 适配器（GitHub API Token + 用户搜索 + 仓库贡献者）
P5-5 [LOW]  实现多源合并 UI（并排对比/差异高亮/手动合并按钮）
P5-6 [LOW]  平台特定反爬配置持久化 + 适配器配置热加载
```

✅ 里程碑：输入一个关键词，从多平台聚合候选人

### P6: 工程化（持续）

```
P6-1 [MED]  单元测试覆盖爬虫解析逻辑 + 去重算法 + 指纹生成（目标 90%+）
P6-2 [MED]  集成测试覆盖 arq 任务队列 + DB 读写 + 账号管理流程
P6-3 [LOW]  Playwright 平台健康探测 CI 定时任务（每周探测 BOSS/猎聘/脉脉可用性）
P6-4 [LOW]  数据归档策略（180 天自动归档 candidates_archive 表）
P6-5 [LOW]  性能优化（大 JSON 存储优化 / 慢查询索引 / 翻页游标）
P6-6 [LOW]  撰写运维手册（故障恢复流程 / 账号维护 / 代理采购指引）
```

✅ 里程碑：CI 全绿

---

*最后更新: 2026-06-11*
*版本: v4.0 (自审核修正版)*
