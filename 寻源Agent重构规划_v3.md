# 寻源 Agent 重构规划 v3 — 完整定稿

> 基于 Momus 审核修正 + 4 个开源仓库调研后的最终规划
> 参照: `talent_sourcing_agent_plan_v2.md` + `ai招聘agent 寻源招聘规划方案.md`

---

## 目录

1. [现状与问题](#一现状与问题)
2. [整体架构](#二整体架构)
3. [技术选型（修正版）](#三技术选型修正版)
4. [模块结构](#四模块结构)
5. [数据模型](#五数据模型)
6. [反爬对抗体系](#六反爬对抗体系)
7. [数据质量控制](#七数据质量控制)
8. [Agent 引擎设计](#八agent-引擎设计)
9. [异步任务体系](#九异步任务体系)
10. [API 设计](#十api-设计)
11. [前端设计](#十一前端设计)
12. [隐私合规](#十二隐私合规)
13. [测试策略](#十三测试策略)
14. [实施路线图](#十四实施路线图)
15. [关键设计决策](#十五关键设计决策)

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
- ❌ 无异步任务队列——采集是同步的
- ❌ 无反爬对抗——中文平台反爬极严
- ❌ 无数据质量链路——采集的数据没校验

### 可复用的现有资产

- ✅ 完整的 Agent 框架（`BaseAgent` / `AgentRegistry` / `PipelineAgent`）
- ✅ Candidate 模型 + CRUD API + 时间线系统
- ✅ Next.js 前端架构 + Tailwind + shadcn/ui
- ✅ 基础设施（PostgreSQL / Redis / Qdrant / MinIO）
- ✅ 工程规范（pre-commit / ruff / mypy / health-check）

---

## 二、整体架构

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              前端层 (Next.js)                                     │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ 寻源工作台      │  │ 任务管理        │  │ 候选人看板      │  │ 平台健康       │  │
│  │ (创建任务)      │  │ (实时进度)      │  │ (多源聚合)      │  │ (状态配置)     │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  └───────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │ REST API + WebSocket
┌──────────────────────────────▼──────────────────────────────────────────────────┐
│                          后端 API 层 (FastAPI)                                    │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  Existing: /api/v1/candidates /jobs /applications /auth /...             │   │
│  │  NEW: /api/v1/sourcing/tasks /platforms /crawl-logs                      │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────────┐
│                        Agent 引擎层                                              │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  Existing: SourcingAgent (逻辑层) / ScreeningAgent / PipelineAgent / ...  │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  NEW: SourcingCrawlAgent     — 采集执行（协调 PlatformAdapter）             │   │
│  │  NEW: SourcingAnalyzeAgent   — LLM 分析（技能/匹配度/摘要）                │   │
│  │  NEW: SourcingMonitorAgent   — 平台健康/成功率监控                         │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────────┐
│                       平台适配层 (Adapter Layer)                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ BOSS直聘     │  │ 猎聘         │  │ 脉脉         │  │ LinkedIn     │        │
│  │ (P1)         │  │ (P5)         │  │ (P5)         │  │ (P5)         │        │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘        │
│  ┌──────────────┐  ┌──────────────┐                                            │
│  │ GitHub       │  │ 知乎/掘金     │  ...                                       │
│  │ (P5)         │  │ (P5)         │                                            │
│  └──────────────┘  └──────────────┘                                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  共享: 反爬引擎 / 代理池管理 / 指纹管理 / 限频器 / 验证码处理               │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────────┐
│                        执行层 (Execution)                                         │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐   │
│  │ Scrapling Spider     │  │ browser-use (有限)   │  │ Celery Workers      │   │
│  │ (主力: 并发/断点续爬) │  │ (仅复杂交互: 登录/    │  │ (异步任务调度)       │   │
│  │                      │  │  验证码/复杂搜索)     │  │                     │   │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────────┐
│                     基础设施 (已有)                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │PostgreSQL │  │ Redis    │  │ Qdrant   │  │ MinIO   │  │ Prometheus+     │  │
│  │(主数据)    │  │(缓存/队列)│  │(向量)    │  │(文件)    │  │ Grafana         │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、技术选型（修正版）

### 核心引擎替换

| 原规划 | 修正后 | 原因 |
|--------|--------|------|
| browser-use 做主力爬取 | **Scrapling** 做主力爬取 | browser-use 每步调 LLM，¥0.01-0.05/步，批量采集成本爆炸 |
| 自己做自适应解析 | **Scrapling 自适应解析** (`auto_save` + `adaptive`) | 平台改版自动恢复，不用手工维护 selector |
| 自己写并发调度 | **Scrapling Spider 框架** | 内置并发、断点续爬、pause/resume、streaming |
| 自己实现反爬 | **Scrapling StealthyFetcher** | 内置 TLS 指纹模仿、Cloudflare Turnstile 绕过 |
| MediaCrawler 参考 | **继续参考架构** | 平台适配器 + CDP 登录 + Cookie 持久化是好模式 |

### 最终技术栈

| 层 | 选型 | 角色 |
|----|------|------|
| **主爬取引擎** | Scrapling (Spider + StealthyFetcher) | 批量并发采集、自适应解析、反爬绕过 |
| **复杂交互** | browser-use (有限使用) | 仅登录、验证码、复杂搜索表单 |
| **浏览器自动化** | Playwright (Scrapling DynamicFetcher 底层) | 渲染 JS 页面 |
| **异步任务** | asyncio (P0-P2) → Celery + Redis (P3+) | 分阶段引入，前期轻量，后期重载 |
| **自适应解析** | Scrapling `auto_save` + `adaptive` | 平台 HTML 改版自动恢复 |
| **向量搜索** | Qdrant (已有) | 技能语义搜索 |
| **LLM 分析** | 现有 LLM 客户端复用 | 复用已有的多模型切换 |
| **前端** | Next.js 14 + Tailwind (已有) | 与现有系统一致 |
| **反爬引擎** | Scrapling StealthFy + 自研代理层 | 指纹伪装 + 代理池 + 限频 |
| **站点经验** | JSON 文件按域名存储 | web-access 模式，跨 session 复用 |

### 为什么 Scrapling 比 browser-use 更适合

```
browser-use 的代价:
  搜索"Python工程师" → 打开 BOSS 首页
                      → 定位搜索框 → 输入 → 点击搜索
                      → 定位结果列表 → 翻页
                      → 每个候选人点开 → 解析
  每步 = LLM 调用, 采集 20 人 ≈ 50+ LLM 调用 ≈ ¥2-5

Scrapling 的代价:
  spider = QuotesSpider()
  spider.start()  # 一行代码并行爬
  # 自适应解析自动处理页面变化
  # 内置反爬绕过
  # 采集 20 人 ≈ 1 个进程 ≈ ¥0 (爬取本身免费)
```

---

## 四、模块结构

### 4.1 后端新增模块

```
apps/api/app/sourcing/
├── __init__.py
├── config.py                      # 寻源专属配置 (Pydantic Settings)
├── dependencies.py                # 依赖注入
│
├── models/                        # SQLAlchemy 模型
│   ├── __init__.py
│   ├── sourcing_task.py            # 采集任务
│   ├── sourcing_candidate.py       # 寻源扩展表 (1:1 关联 Candidate)
│   ├── crawl_log.py                # 采集日志
│   └── platform_config.py          # 平台配置
│
├── schemas/                       # Pydantic DTO
│   ├── __init__.py
│   ├── task.py
│   ├── candidate.py
│   ├── platform.py
│   └── stats.py
│
├── api/                           # API 路由
│   ├── __init__.py
│   ├── tasks.py                   # /api/v1/sourcing/tasks
│   ├── platforms.py               # /api/v1/sourcing/platforms
│   ├── candidates.py              # /api/v1/sourcing/candidates
│   └── stats.py                   # /api/v1/sourcing/stats
│
├── services/                      # 业务逻辑
│   ├── __init__.py
│   ├── task_service.py            # 任务编排
│   ├── crawl_service.py           # 采集调度
│   └── merge_service.py           # 多源数据合并
│
├── adapters/                      # 平台适配器 (插件式)
│   ├── __init__.py                # 自动注册
│   ├── base.py                    # PlatformAdapter 抽象基类
│   ├── boss_zhipin.py             # BOSS直聘
│   ├── liepin.py                  # 猎聘
│   ├── maimai.py                  # 脉脉
│   ├── linkedin.py                # LinkedIn
│   └── github.py                  # GitHub
│
├── engine/                        # 反爬引擎
│   ├── __init__.py
│   ├── anti_crawl.py              # 反爬对抗协调器
│   ├── fingerprint.py             # 浏览器指纹管理
│   ├── proxy_pool.py              # 代理池
│   └── captcha.py                 # 验证码处理
│
├── tasks/                         # 异步任务 (P3 后转 Celery)
│   ├── __init__.py
│   ├── crawl_task.py              # 采集任务
│   ├── analyze_task.py            # 分析任务
│   └── aggregate_task.py          # 聚合去重
│
├── agents/                        # Agent 引擎集成
│   ├── __init__.py
│   ├── crawl_agent.py             # SourcingCrawlAgent
│   ├── analyze_agent.py           # SourcingAnalyzeAgent
│   └── monitor_agent.py           # SourcingMonitorAgent
│
└── experience/                    # 站点经验 (web-access 模式)
    ├── __init__.py
    └── store.py                   # 按域名存储操作经验
```

### 4.2 前端新增模块

```
apps/web/app/sourcing/
├── page.tsx                       # 寻源工作台首页
├── layout.tsx                     # 布局
│
├── tasks/
│   ├── page.tsx                   # 任务列表
│   └── [taskId]/
│       └── page.tsx               # 任务详情 (实时进度 WebSocket)
│
├── candidates/
│   ├── page.tsx                   # 寻源候选人列表
│   └── [candidateId]/
│       └── page.tsx               # 多源聚合详情
│
└── platforms/
    └── page.tsx                   # 平台配置与健康状态
```

---

## 五、数据模型

### 5.1 设计原则

- Candidate 表**直接加新字段**（不是扩展表），全 `nullable=True` 无损兼容
- 所有 sourcing 新表用独立前缀 `sourcing_`
- 统一 ULID 主键，与现有系统一致

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
    BANNED = "banned"         # IP 被封
    CAPTCHA = "captcha"       # 触发验证码
    TIMEOUT = "timeout"
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
    captcha_solved: Mapped[bool] = mapped_column(Boolean, default=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # 关联
    task = relationship("SourcingTask", back_populates="logs")
```

### 5.4 Candidate 扩展字段（改现有表）

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

    config: Mapped[dict] = mapped_column(JSON, default=dict, comment="平台特有配置")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")
    health_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

### 5.6 表关系总图

```
sourcing_tasks
    │
    ├── 1:N ── crawl_logs
    │
    └── 1:N ── candidates (通过 sourcing_task_id)
                     │
                     └── 与现有 Application / Interview / Evaluation 等关系不变

sourcing_platform_configs (独立配置表，不关联业务)
```

---

## 六、反爬对抗体系

### 总体策略

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        反爬对抗引擎 (Anti-Crawl Engine)                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  L1 指纹伪装层 (Scrapling StealthyFetcher 内置)                          │
│  ├── TLS 指纹模仿 (Chrome/Firefox/Safari 最新版本)                       │
│  ├── HTTP/3 (QUIC) 支持                                                  │
│  ├── 自动处理 Cloudflare Turnstile/Interstitial                          │
│  ├── DNS 泄漏防护 (DoH 通过 Cloudflare)                                  │
│  └── 域名拦截 + 广告拦截 (~3500 追踪域名)                                │
│                                                                         │
│  L2 请求调度层 (自研)                                                    │
│  ├── 代理池: 住宅代理 + 数据中心代理 + 移动代理 (付费)                    │
│  │   └── 候选: BirdProxies / 9Proxy / 自建 Squid 池                     │
│  ├── 智能限频: 根据 HTTP 响应头/错误率动态调整间隔                        │
│  │   └── Scrapling Spider 内置 per-domain throttling                     │
│  ├── 指数退避 + 抖动: 失败时 2^n * 60s + random(0, 30)                  │
│  └── 会话轮换: Cookie 定期刷新, 不同任务用不同 session                    │
│                                                                         │
│  L3 浏览器行为模拟 (Scrapling DynamicFetcher + 自研)                     │
│  ├── CDP 模式复用本地 Chrome 登录态 (MediaCrawler 模式)                  │
│  ├── Scrapling DynamicSession 管理浏览器 tab 池                          │
│  ├── 鼠标轨迹/滚动/点击模拟 (仅 browser-use 场景)                        │
│  └── 页面停留时间随机化                                                  │
│                                                                         │
│  L4 验证码应对层                                                        │
│  ├── 滑块验证码: Scrapling StealthyFetcher 已内置绕过部分                 │
│  ├── 图像验证码: 2Captcha / CapSolver 打码服务 (备用)                    │
│  ├── 打码成本: ~¥2-5/次, 仅失败时启用                                   │
│  └── 触发率监控: >20% 触发验证码 → 切换代理/暂停采集                     │
│                                                                         │
│  L5 账号安全层                                                          │
│  ├── 多账号矩阵: 主号(日常) + 备用号(降级) + 采集号(高频率)              │
│  ├── 账号健康度: 登录态/封禁状态定期探测                                 │
│  └── Cookie 持久化: Redis 加密存储, 跨 session 复用                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Scrapling 各 Fetcher 使用场景

| Fetcher | 反爬等级 | 是否启动浏览器 | 适用平台 |
|---------|---------|--------------|---------|
| `Fetcher` | 低 | 否 | GitHub API、知乎 API |
| `FetcherSession` | 中 | 否 (HTTP) | 掘金、CSDN 静态页 |
| **`StealthyFetcher`** | **高** | **Playwright 隐式** | **BOSS直聘、猎聘、脉脉** |
| `DynamicFetcher` | 中 | Playwright 显式 | 需要 JS 渲染但不需反爬的场景 |

### 代理池设计

```python
class ProxyPool:
    """三层代理池"""

    TIERS = {
        "premium":   {"type": "residential", "cost": "¥0.8/GB"},   # 住宅代理
        "standard":  {"type": "datacenter",  "cost": "¥0.2/GB"},   # 数据中心
        "mobile":    {"type": "mobile",      "cost": "¥3/GB"},     # 移动代理(备用)
    }

    async def get_proxy(self, platform: str, anti_crawl_level: int) -> str:
        """按平台反爬等级返回对应 tier 的代理"""
        if anti_crawl_level >= 4:
            return await self._acquire("premium")
        elif anti_crawl_level >= 2:
            return await self._acquire("standard")
        return None  # 直连

    async def report_failure(self, proxy: str, platform: str):
        """报告代理失败, 自动降级"""
```

---

## 七、数据质量控制

```
原始 HTML / JSON
    │
    ▼
┌──────────────────────────────────────┐
│  L1 解析校验 (Scrapling 自适应解析)    │
│  ├── Scrapling css()/xpath() 提取    │
│  ├── auto_save=True 存原始选择器      │
│  ├── adaptive=True 平台改版后自动恢复  │
│  └── 关键字段缺失率 > 30% → 标记      │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│  L2 数据清洗                          │
│  ├── 手机号格式校验 (正则)             │
│  ├── 邮箱格式校验                      │
│  ├── 公司名标准化 (规则 + NLP)         │
│  ├── 技能标签归一化 (同义词合并)        │
│  └── 薪资单位统一 (万/年 → 千/月)      │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│  L3 多源交叉验证                       │
│  ├── 同一候选人在不同平台数据比对       │
│  ├── 时间线一致性 (工作年限 vs 毕业时间) │
│  ├── 矛盾数据标记                      │
│  └── 置信度评分                        │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│  L4 AI 增强 (LLM)                     │
│  ├── 职业摘要生成                      │
│  ├── 技能推断 (从工作经历中提取)        │
│  ├── 匹配度评分 (与 JD 对比)           │
│  ├── 嵌入向量生成 → Qdrant            │
│  └── 置信度 < 0.7 → 标记 "AI推测"     │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│  L5 人工审核                           │
│  ├── 高价值候选人强制人工确认           │
│  ├── 争议数据仲裁                      │
│  └── 审核结果回馈 → 改进解析规则        │
└──────────────────────────────────────┘
```

---

## 八、Agent 引擎设计

### 8.1 PlatformAdapter 接口（核心抽象）

```python
class CrawlResult(BaseModel):
    success: bool
    candidates: list[dict] = []
    error_message: str | None = None
    next_page_url: str | None = None
    rate_limit_info: dict | None = None
    captcha_triggered: bool = False
    proxy_used: str | None = None

class PlatformAdapter(ABC):
    """所有平台适配器的基类 — 利用 Scrapling 各 Fetcher 实现"""

    # 类属性（元数据，子类覆盖）
    name: str                    # 平台标识, e.g. "boss_zhipin"
    display_name: str            # "BOSS直聘"
    category: str                # "job_board" / "social" / "code"
    anti_crawl_level: int        # 1-5
    requires_login: bool
    use_stealth: bool = True     # 是否启用 StealthyFetcher

    def __init__(self, config: dict, proxy_pool: ProxyPool):
        self.config = config
        self.proxy_pool = proxy_pool
        self._session = None
        self._consecutive_failures = 0

    @abstractmethod
    async def search(self, keyword: str, **filters) -> CrawlResult:
        """关键词搜索 → 返回候选人列表"""
        pass

    @abstractmethod
    async def get_detail(self, url: str) -> CrawlResult:
        """候选人详情页"""
        pass

    @abstractmethod
    async def parse_list(self, html: str) -> list[dict]:
        """解析列表页 — 使用 Scrapling 自适应解析"""
        pass

    @abstractmethod
    async def parse_detail(self, html: str) -> dict:
        """解析详情页"""
        pass

    # 钩子
    async def pre_search(self, keyword: str) -> None: ...
    async def post_search(self, result: CrawlResult) -> CrawlResult: ...

    # 健康管理
    @property
    def health_status(self) -> str: ...
    def record_failure(self): ...
    def record_success(self): ...
```

### 8.2 BOSS直聘适配器示例（Scrapling 模式）

```python
class BossZhipinAdapter(PlatformAdapter):
    name = "boss_zhipin"
    display_name = "BOSS直聘"
    category = "job_board"
    anti_crawl_level = 4
    requires_login = True
    use_stealth = True

    async def search(self, keyword: str, city: str = None, **filters) -> CrawlResult:
        # 1. 走 Scrapling StealthySession 连接 CDP Chrome
        from scrapling.fetchers import StealthySession

        async with StealthySession(
            headless=False,          # 开发时可见
            solve_cloudflare=True,   # 自动绕过 Cloudflare
            proxy=await self.proxy_pool.get_proxy("boss_zhipin", 4),
        ) as session:
            url = self._build_search_url(keyword, city)
            page = await session.fetch(url, network_idle=True)

            # 检测是否触发验证码
            if "captcha" in page.url.lower():
                return CrawlResult(success=False, captcha_triggered=True,
                                   error_message="验证码触发")

            # 2. 自适应解析候选人列表
            #    auto_save=True → 存当前 selector, 平台改版后 adaptive=True 自动恢复
            items = page.css('.candidate-card', auto_save=True)
            candidates = []
            for item in items[:20]:  # 前20人
                candidate = {
                    "name": item.css('.name::text').get(),
                    "title": item.css('.title::text').get(),
                    "company": item.css('.company::text').get(),
                    "salary": item.css('.salary::text').get(),
                    "url": item.css('a::attr(href)').get(),
                }
                candidates.append(candidate)

            return CrawlResult(success=True, candidates=candidates)

    async def parse_detail(self, html: str) -> dict:
        # 使用 Scrapling 自适应解析候选人详情
        from scrapling.parser import Selector
        page = Selector(html)
        return {
            "name": page.css('.name::text', auto_save=True).get(),
            "experience": page.css('.exp::text', auto_save=True).getall(),
            "skills": page.css('.skill-tag::text', auto_save=True).getall(),
            # ...
        }
```

### 8.3 自动注册机制

```python
# apps/api/app/sourcing/adapters/__init__.py
import importlib
import pkgutil

_ADAPTERS: dict[str, type[PlatformAdapter]] = {}

def discover_adapters():
    """自动扫描 adapters/ 目录注册, 新增平台只需加一个文件"""
    for _, name, _ in pkgutil.iter_modules(__path__):
        if name.startswith("_") or name == "base":
            continue
        module = importlib.import_module(f".{name}", __package__)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                issubclass(attr, PlatformAdapter) and
                attr is not PlatformAdapter and
                hasattr(attr, "name")):
                _ADAPTERS[attr.name] = attr

def get_adapter(name: str) -> type[PlatformAdapter]:
    if name not in _ADAPTERS:
        raise ValueError(f"Unknown platform: {name}")
    return _ADAPTERS[name]

def list_adapters() -> list[dict]: ...

# 模块导入时自动发现
discover_adapters()
```

### 8.4 SourcingCrawlAgent

```python
class SourcingCrawlAgent(BaseAgent):
    """采集执行 Agent — 真正的猎手"""

    output_keys = ["candidates", "task_result"]

    async def run(self, input_data: dict) -> dict:
        task = input_data["task"]

        # 1. 解析任务 → 确定采集策略
        platforms = task.platforms
        keyword = task.keyword

        # 2. 并行调用多个 PlatformAdapter
        results = {}
        for platform in platforms:
            adapter_cls = get_adapter(platform)
            adapter = adapter_cls(config=..., proxy_pool=...)
            result = await adapter.search(keyword, **task.filters)
            results[platform] = result

            # 处理验证码/被封
            if result.captcha_triggered:
                # 切换代理重试 / 通知人工
                ...

        # 3. 去重 → 写入 DB
        all_candidates = self._deduplicate(results)
        saved = await self._save_candidates(all_candidates, task.id)

        # 4. 触发分析
        if saved:
            analyze_candidates_task.delay(saved, task.id)

        return self.format_result("completed", {
            "candidates": saved,
            "platform_results": {k: v.dict() for k, v in results.items()},
        }, f"采集完成, 共 {len(saved)} 人")
```

### 8.5 SourcingAnalyzeAgent

```python
class SkillAssessment(BaseModel):
    skill_name: str
    proficiency: int = Field(ge=1, le=5)
    evidence: str
    confidence: float = Field(ge=0, le=1)

class CareerTrajectory(BaseModel):
    current_level: str
    trajectory: str  # 上升/平稳/下降
    stability_score: float
    red_flags: list[str]

class MatchAnalysis(BaseModel):
    overall_score: float
    dimension_scores: dict[str, float]
    strengths: list[str]
    gaps: list[str]
    recommendation: str

class SourcingAnalyzeAgent(BaseAgent):
    """分析 Agent — LLM 给候选人打标签"""

    async def run(self, input_data: dict) -> dict:
        candidate = input_data["candidate"]
        jd = input_data.get("jd")

        # 1. 技能提取 (LLM)
        skills = await self._extract_skills(candidate)

        # 2. 职业轨迹
        career = await self._analyze_career(candidate)

        # 3. 嵌入向量 → Qdrant
        vector = await self._embed(skills)

        # 4. 匹配度 (如有 JD)
        match = None
        if jd:
            match = await self._match_jd(candidate, jd)

        return {"skills": skills, "career": career, "match": match}
```

---

## 九、异步任务体系

### 分阶段策略

| 阶段 | 方案 | 原因 |
|------|------|------|
| **P0-P2** (骨架→单平台) | `asyncio.create_task` + Redis Stream | 快速启动，不引入新依赖 |
| **P3+** (多平台+重试) | **Celery + Redis** | 生产级重试/优先级/监控/队列隔离 |

### P0-P2 轻量方案

```python
# apps/api/app/sourcing/tasks/crawl_task.py
import asyncio
from redis import Redis

class TaskDispatcher:
    """基于 asyncio 的轻量任务调度（P0-P2 过渡方案）"""

    def __init__(self, redis: Redis):
        self.redis = redis
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def dispatch_crawl(self, task_id: str, platform: str, keyword: str):
        """异步执行单平台采集"""
        loop = asyncio.get_event_loop()
        crawl_task = loop.create_task(self._execute_crawl(task_id, platform, keyword))
        self._running_tasks[task_id] = crawl_task
        # 状态存入 Redis，前端 WebSocket 轮询
        return crawl_task

    async def _execute_crawl(self, task_id: str, platform: str, keyword: str):
        try:
            adapter = get_adapter(platform)(config, proxy_pool)
            result = await adapter.search(keyword)
            # 存结果
            await self._save_results(task_id, result)
        except Exception as e:
            await self._mark_failed(task_id, str(e))
            raise
        finally:
            self._running_tasks.pop(task_id, None)

    async def cancel(self, task_id: str):
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
```

### P3+ Celery 方案

```python
# apps/api/app/sourcing/tasks/celery_app.py
from celery import Celery

celery_app = Celery(
    "sourcing",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    task_track_started=True,
    task_time_limit=3600,           # 最长1小时
    worker_prefetch_multiplier=1,   # 公平调度
    task_acks_late=True,            # 完成后才确认
    worker_max_tasks_per_child=50,  # 防内存泄漏
)

# 三个队列隔离
# celery -A sourcing.tasks.celery_app worker -Q crawl -c 2
# celery -A sourcing.tasks.celery_app worker -Q analyze -c 4
# celery -A sourcing.tasks.celery_app worker -Q export -c 1
```

---

## 十、API 设计

### 10.1 端点列表

```
# 任务管理
GET    /api/v1/sourcing/tasks              → 任务列表 (分页+筛选+排序)
POST   /api/v1/sourcing/tasks              → 创建采集任务
GET    /api/v1/sourcing/tasks/{id}         → 任务详情+实时进度
DELETE /api/v1/sourcing/tasks/{id}         → 取消任务
GET    /api/v1/sourcing/tasks/{id}/logs    → 任务采集日志

# 平台管理
GET    /api/v1/sourcing/platforms           → 平台列表+健康状态
PUT    /api/v1/sourcing/platforms/{name}   → 更新平台配置
POST   /api/v1/sourcing/platforms/{name}/health-check → 手动健康检查

# 寻源候选人
GET    /api/v1/sourcing/candidates          → 寻源候选人列表
GET    /api/v1/sourcing/candidates/{id}    → 候选人多源聚合详情
POST   /api/v1/sourcing/candidates/{id}/analyze → 触发 AI 分析
POST   /api/v1/sourcing/candidates/{id}/merge   → 手动合并多源

# 统计
GET    /api/v1/sourcing/stats              → 采集统计 (总量/成功率/趋势)

# WebSocket 实时进度
WS     /ws/sourcing/tasks/{id}             → 任务实时进度推送
```

### 10.2 鉴权

- 复用现有 org-scoped RBAC
- `sourcing:task:create` / `sourcing:task:read` / `sourcing:task:cancel` 权限
- 平台配置仅 `admin` 角色可改

### 10.3 WebSocket 推送

```python
# WebSocket 推送任务实时状态
class TaskProgress(BaseModel):
    task_id: str
    platform: str
    status: str          # running / completed / failed
    found: int           # 当前已采集人数
    total_estimate: int  # 预估总量
    error: str | None    # 当前错误
    progress_pct: float  # 0-100
```

---

## 十一、前端设计

### 11.1 页面组件树

```
sourcing/
├── layout.tsx                    # 布局 (Nav + Sidebar)
├── page.tsx                      # 工作台
│   ├── QuickCreateForm           # 快速创建任务表单
│   ├── RecentTasks               # 最近任务列表
│   └── PlatformHealthCards        # 各平台健康状态卡片
│
├── tasks/
│   ├── page.tsx                  # 任务列表
│   │   ├── TaskFilters           # 状态/平台/日期筛选
│   │   ├── TaskTable             # 任务数据表格
│   │   └── Pagination            # 分页
│   │
│   └── [taskId]/
│       └── page.tsx              # 任务详情
│           ├── TaskHeader        # 标题/状态/操作按钮
│           ├── ProgressTimeline  # 各平台执行时间线
│           ├── PlatformCards     # 各平台卡片 (状态/人数/耗时)
│           ├── CandidatePreview  # 已采集候选人预览
│           └── CrawlLogPanel     # 采集日志 (错误/告警)
│
├── candidates/
│   ├── page.tsx                  # 寻源候选人列表
│   │   ├── SearchFilters        # 关键词/平台/匹配度筛选
│   │   ├── CandidateTable       # 候选人数据表格
│   │   └── BulkActions          # 批量操作 (合并/导出/标记)
│   │
│   └── [candidateId]/
│       └── page.tsx              # 多源聚合详情
│           ├── IdentityCard       # 基本信息卡片 (多源合并后)
│           ├── SourceTabs         # 各平台原始数据 tab
│           ├── AIAnalysisPanel    # AI 分析结果 (技能雷达/匹配度)
│           └── Timeline           # 采集/分析时间线
│
└── platforms/
    └── page.tsx                  # 平台配置
        ├── PlatformTable        # 平台列表 (健康状态/等级)
        └── PlatformConfigModal  # 编辑配置弹窗
```

### 11.2 数据流

```
API 请求 ─→ TanStack Query (React Query) ─→ Zustand (UI 状态)
                                         ─→ Zustand (WebSocket 连接池)

WebSocket 实时推送 ─→ Zustand taskStore ─→ 组件订阅
```

### 11.3 关键交互

- **创建任务**：选平台（多选）+ 输入关键词 + 可选筛选条件 → POST → 跳转任务详情
- **任务详情**：WebSocket 实时更新进度条、候选人列表逐步出现
- **候选人对比**：多平台数据 tab 切换，AI 分析结果在一个页面展示
- **平台健康**：颜色指示（绿/黄/红），最近一次探测时间

---

## 十二、隐私合规

### 12.1 数据采集边界

- **只采集公开可见信息**：姓名、工作经历、技能标签、教育背景
- **不采集**：身份证号、家庭住址、银行账号、社保信息
- **联系方式**：手机/邮箱只作为去重指纹，不对外展示

### 12.2 数据存储策略

```python
# 手机号存储脱敏
class Candidate(Base):
    phone: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="手机号 (存储时 AES 加密)"
    )
    # 读取时自动脱敏: 138****1234
```

### 12.3 数据生命周期

| 策略 | 实现 |
|------|------|
| 自动清理 | 超过 180 天未更新的候选人数据自动归档 |
| 手动删除 | DELETE API 触发级联删除 (`sourcing_task_id` 置空) |
| 审计日志 | 所有采集/查看/导出操作记录 `audit_logs` 表 |
| 用户授权 | 候选人可申请删除自己的数据 (预留接口) |

### 12.4 法律合规

- 遵守《个人信息保护法》(PIPL)
- 控制采集频率，不冲击平台正常服务
- 不绕过登录墙/付费墙
- 采集数据仅用于内部招聘流程

---

## 十三、测试策略

### 层级

| 层级 | 工具 | 覆盖内容 | 目标 |
|------|------|---------|------|
| **Unit** | pytest + pytest-asyncio | PlatformAdapter 解析逻辑、去重算法 | 90%+ |
| **Mock** | pytest + respx + unittest.mock | 模拟 HTTP 响应的解析测试 | 不依赖外部 |
| **Integration** | pytest + Testcontainers | DB 读写、Celery 任务 | 真实 DB |
| **E2E** | Playwright | 真实浏览器访问测试平台 (用测试账号) | 冒烟 |

### 关键测试用例

```python
# tests/unit/test_adapters/test_parse.py
class TestBossZhipinParse:
    """使用 Scrapling 解析器 + 本地 HTML fixture 测试, 不依赖真实网站"""

    def test_parse_list_page(self, boss_list_html_fixture):
        adapter = BossZhipinAdapter(config={}, proxy_pool=MagicMock())
        result = adapter.parse_list(boss_list_html_fixture)
        assert len(result) > 0
        assert result[0]["name"] is not None

    def test_parse_with_adaptive(self):
        """模拟平台改版后, adaptive=True 仍能解析"""
        # Scrapling 的 auto_save 存了原始 selector
        # 改版后 adaptive=True 自动定位新元素
        pass
```

---

## 十四、实施路线图

### 分阶段计划

| 阶段 | 周期 | 目标 | 交付物 | 里程碑 |
|------|------|------|--------|--------|
| **P0 骨架** | 1 周 | 项目结构 + 基础模型 | sourcing/ 目录、模型 migration、API 空路由、Scrapling 依赖安装 | 可创建空任务 |
| **P1 BOSS直聘** | 2-3 周 | 单平台采集跑通（有限） | BOSS适配器、Scrapling Spider 采集、数据入库、反爬基本策略 | 输入关键词→存到 DB |
| **P2 前端** | 1-2 周 | 前后端联调 | 任务创建/监控/候选人查看 WebSocket 实时 | 可在 UI 操作 |
| **P3 健壮性** | 1-2 周 | 生产可用 | 代理池、重试/退避、错误恢复、限频 | 连续 24h 不中断 |
| **P4 AI 分析** | 1-2 周 | 智能化 | LLM 分析链路、Qdrant 向量、匹配度 | 候选人自动评分 |
| **P5 多平台** | 3-4 周 | 覆盖 4 平台 | 猎聘/脉脉/LinkedIn/GitHub + 多源去重 | 多平台聚合 |
| **P6 工程化** | 持续 | 质量保障 | 测试覆盖 > 80%、CI/CD、监控告警 | CI 全绿 |

### 依赖关系

```
P0 (骨架) ──→ P1 (BOSS直聘) ──→ P2 (前端) ──→ P3 (健壮性)
                                  │               │
                                  └──→ P4 (AI分析) ┘
                                        │
                                        └──→ P5 (多平台)
                                              │
                                              └──→ P6 (工程化)
```

---

## 十五、关键设计决策

### D1: 直接改 Candidate 表 vs 扩展表
**决策**: 直接改 Candidate 表加字段 (全 nullable)
**理由**: 现有 Candidate 只有 63 行、14 个字段，全 nullable 无损兼容。扩展表 1:1 查询复杂、ORM 关联多一层。

### D2: Scrapling vs browser-use
**决策**: Scrapling 做主力，browser-use 仅复杂交互
**理由**: browser-use 每步走 LLM (¥0.01-0.05/步)，批量采集经济上不可行。Scrapling 免费、支持并发/断点续爬/自适应解析。

### D3: asyncio → Celery 分阶段
**决策**: P0-P2 用 asyncio + Redis Stream 轻量调度，P3+ 转 Celery
**理由**: 初期引入 Celery 成本高（新 Docker service、新依赖、部署复杂度），asyncio 足以支撑单平台 MVP。

### D4: 不引入 Elasticsearch
**决策**: 候选人搜索复用现有 PostgreSQL 全文索引 + Qdrant 向量搜索
**理由**: 现有系统已有 Qdrant，增加 ES 带来运维成本。PostgreSQL 全文搜索对候选人搜索场景足够。

### D5: 适配器插件化自动注册
**决策**: pkgutil 自动发现，新增平台=写一个文件
**理由**: MediaCrawler 已验证此模式可行。低心智负担，高可扩展性。

### D6: Scrapling 自适应解析替代手工维护 selector
**决策**: 使用 `auto_save=True` + `adaptive=True`
**理由**: 平台平均每 2-3 月改版一次 HTML，手工维护不可持续。Scrapling 的智能定位算法可自动恢复。

### D7: 采集任务状态用部分成功而非整体失败
**决策**: 多平台采集时，单个平台失败不影响其他平台
**理由**: BOSS 被封 ≠ 猎聘不能采。`SourcingTaskStatus.PARTIAL` 状态表达"部分成功"。

### D8: 站点经验积累（web-access 模式）
**决策**: 按域名存 JSON 经验文件，跨 session 复用
**理由**: BOSS直聘的反爬策略会变，上次成功的代理/指纹组合不一定下次能用。经验积累可逐步降低失败率。

---

## 附录：成本估算

| 项目 | P0-P2 (月) | P3-P4 (月) | P5-P6 (月) |
|------|-----------|-----------|-----------|
| LLM API (分析) | ¥0 | ¥200-500 | ¥500-1000 |
| 代理 IP (住宅) | ¥0 (直连) | ¥100-300 | ¥300-800 |
| 打码服务 | ¥0 | ¥0-100 | ¥100-300 |
| 服务器 (已有) | ¥0 | ¥0 | ¥0 |
| **合计** | **¥0/月** | **¥300-900/月** | **¥900-2100/月** |

---

*最后更新: 2026-06-11*
*版本: v3.0 (Momus 审核修正版)*
