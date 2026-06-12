# AI 人才寻源 Agent — 技术规划

> 核心目标：抓取候选人信息到本地数据库，供后续检索、分析、联系
> 对标：Pin / SeekOut（全行业覆盖），但走开源 + 低成本路线
> 技术栈：browser-use + Scrapling + MediaCrawler + web-access
>
> ## 📚 参考开源项目
>
> | 项目 | GitHub | Stars | 角色 |
> |------|--------|-------|------|
> | **browser-use** | https://github.com/browser-use/browser-use | ~98,100 | 浏览器自动化引擎（给 AI Agent 一个真实浏览器） |
> | **Scrapling** | https://github.com/D4Vinci/Scrapling | ~62,400 | 自适应 Web 爬取框架（页面改版自动适应） |
> | **MediaCrawler** | https://github.com/NanmiCoder/MediaCrawler | ~50,400 | 多平台数据采集架构（CDP 模式 + 平台适配） |
> | **web-access** | https://github.com/eze-is/web-access | 中等（~1,000-2,000） | Agent 联网调度层（三层通道 + 经验积累） |
> | **OWL** | https://github.com/camel-ai/owl | ~19,800 | 多智能体协作框架（角色分工参考） |

---

## 一、系统架构

```
┌──────────────────────────────────────────────────────────┐
│                     用户界面层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  WebUI (Gradio)│  │  CLI         │  │  API 接口     │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
├─────────┼─────────────────┼─────────────────┼───────────┤
│         │                 │                 │           │
│     ┌────▼─────────────────▼─────────────────▼───────┐  │
│     │              Agent 调度层                       │  │
│     │                                                │  │
│     │  ┌──────────┐  ┌──────────┐  ┌──────────┐    │  │
│     │  │ 搜索Agent │  │ 采集Agent │  │ 分析Agent │    │  │
│     │  └────┬─────┘  └────┬─────┘  └────┬─────┘    │  │
│     └───────┼──────────────┼──────────────┼─────────┘  │
│             │              │              │            │
├─────────────┼──────────────┼──────────────┼────────────┤
│             │              │              │            │
│     ┌───────▼──────────────▼──────────────▼─────────┐  │
│     │            浏览器自动化引擎                     │  │
│     │   ┌──────────────────┐   ┌──────────────┐    │  │
│     │   │  browser-use     │   │  Scrapling   │    │  │
│     │   │  (浏览器操作)     │   │  (智能解析)   │    │  │
│     │   └──────────────────┘   └──────────────┘    │  │
│     └──────────────────────┬───────────────────────┘  │
│                            │                          │
├────────────────────────────┼──────────────────────────┤
│                            │                          │
│     ┌──────────────────────▼───────────────────────┐  │
│     │            平台适配层                         │  │
│     │  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────┐ │  │
│     │  │ BOSS直聘│ │ 猎聘  │ │ 脉脉  │ │GitHub │ │  │
│     │  └────────┘ └────────┘ └────────┘ └───────┘ │  │
│     │  ┌────────┐ ┌────────┐ ┌────────┐           │  │
│     │  │LinkedIn│ │ 知乎  │ │ 掘金  │ ...       │  │
│     │  └────────┘ └────────┘ └────────┘           │  │
│     └──────────────────────┬───────────────────────┘  │
│                            │                          │
├────────────────────────────┼──────────────────────────┤
│                            │                          │
│     ┌──────────────────────▼───────────────────────┐  │
│     │            本地数据存储                       │  │
│     │  ┌────────────────┐  ┌────────────────────┐  │  │
│     │  │ PostgreSQL /   │  │  ChromaDB(向量)    │  │  │
│     │  │ SQLite (MVP)   │  │  技能语义搜索      │  │  │
│     │  └────────────────┘  └────────────────────┘  │  │
│     └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 二、数据流向

```
用户输入关键词/JD
       │
       ▼
  搜索 Agent
  (决定搜哪个平台、用什么策略)
       │
       ▼
  browser-use 启动浏览器
  (复用本地 Chrome 登录态 → CDP 模式)
       │
       ▼
  平台适配层
  (输入关键词 → 点击搜索 → 进入候选人列表 → 逐页采集)
       │
       ▼
  Scrapling 智能解析
  (从 HTML/DOM 提取结构化候选人数据)
       │
       ▼
  本地数据库存储
  (候选人基本信息 + 技能标签 + 来源平台 + 采集时间)
       │
       ▼
  分析 Agent
  (LLM 评分、匹配度分析、职业轨迹分析)
       │
       ▼
  用户查看结果 / 导出
```

---

## 三、数据模型设计

### 3.1 候选人主表（candidates）

```sql
CREATE TABLE candidates (
    id              INTEGER PRIMARY KEY,
    name            TEXT,              -- 姓名
    gender          TEXT,              -- 性别（如能获取）
    age             INTEGER,           -- 年龄（如能获取）
    phone           TEXT,              -- 联系方式（脱敏）
    email           TEXT,              -- 邮箱
    current_company TEXT,              -- 当前公司
    current_title   TEXT,              -- 当前职位
    location        TEXT,              -- 城市
    experience_years INTEGER,          -- 工作年限
    salary_expectation INTEGER,         -- 期望薪资
    skills          TEXT,              -- 技能标签 (JSON数组)
    summary         TEXT,              -- 职业摘要 (LLM生成)
    match_score     REAL,              -- 匹配度评分 (0-100)
    source_platform TEXT,              -- 来源平台 (boss/zhipin)
    source_url      TEXT,              -- 原始链接
    source_type     TEXT,              -- 来源类型 (profile/posting)
    raw_data        TEXT,              -- 原始数据 (JSON)
    first_crawled   TEXT,              -- 首次采集时间
    last_updated    TEXT,              -- 最后更新时间
    tags            TEXT,              -- 用户自定义标签 (JSON)
    status          TEXT DEFAULT 'new', -- new / reviewed / contacted / archived
    notes           TEXT               -- 备注
);

CREATE INDEX idx_name ON candidates(name);
CREATE INDEX idx_company ON candidates(current_company);
CREATE INDEX idx_title ON candidates(current_title);
CREATE INDEX idx_skills ON candidates(skills);
CREATE INDEX idx_platform ON candidates(source_platform);
CREATE INDEX idx_score ON candidates(match_score);
```

### 3.2 平台适配配置表（platforms）

```sql
CREATE TABLE platforms (
    id              INTEGER PRIMARY KEY,
    name            TEXT UNIQUE,       -- 平台名
    url_pattern     TEXT,              -- URL 模式
    login_required  BOOLEAN DEFAULT FALSE,
    stealth_level   TEXT DEFAULT 'medium', -- low/medium/high
    rate_limit      INTEGER DEFAULT 2, -- 请求间隔(秒)
    config          TEXT,              -- 平台特有配置 (JSON)
    enabled         BOOLEAN DEFAULT TRUE
);
```

### 3.3 采集日志表（crawl_logs）

```sql
CREATE TABLE crawl_logs (
    id              INTEGER PRIMARY KEY,
    platform        TEXT,
    query           TEXT,              -- 搜索关键词
    url             TEXT,              -- 目标URL
    status          TEXT,              -- success / failed / banned
    candidates_found INTEGER,
    error_message   TEXT,
    started_at      TEXT,
    finished_at     TEXT,
    duration_seconds INTEGER
);
```

---

## 四、平台适配策略

### 4.1 各平台反爬等级

| 平台 | 反爬等级 | 推荐策略 |
|------|----------|----------|
| **BOSS直聘** | 🔴 高 | CDP模式 + 代理 + 模拟人工间隔 |
| **猎聘** | 🔴 高 | CDP模式 + 代理 + 请求间隔 |
| **脉脉** | 🔴 高 | CDP模式 + 代理 + 限频 |
| **LinkedIn** | 🟡 中高 | CDP模式 + 代理（需科学上网） |
| **GitHub** | 🟢 低 | 直接 API / HTTP 请求 |
| **知乎** | 🟢 低 | 直接 HTTP 请求 |
| **掘金/CSDN** | 🟢 低 | 直接 HTTP 请求 |

### 4.2 平台采集顺序（MVP 优先级）

**第一优先级**（必须）：
1. **BOSS直聘** — 最大的人才库，中国最主流招聘平台
2. **猎聘** — 中高端人才为主

**第二优先级**（扩展）：
3. **脉脉** — 职业社交，有主动求职者
4. **LinkedIn** — 外企/出海/高端人才（需科学上网）

**第三优先级**（能力验证）：
5. **GitHub** — 技术人才（简单，有 API）
6. **知乎/掘金/CSDN** — 技术深度评估

### 4.3 每个平台采集什么

**BOSS直聘**：
- 候选人基本信息：姓名、城市、工作年限
- 当前/最近公司、职位
- 期望薪资、期望职位
- 工作经历（最近几份）
- 技能标签（从工作经历中提取）
- 教育背景

**猎聘**：
- 完整简历信息
- 在线简历预览
- 薪资水平
- 猎头关注度

**脉脉**：
- 职业档案
- 动态/发言（评估沟通能力）
- 人脉关系

**GitHub**：
- 技术栈（从项目/提交中提取）
- 开源贡献度
- 代码质量（Stars/PR）

---

## 五、MVP 分阶段规划

### Phase 0: 环境搭建 + 原型验证（3-5 天）

**目标**：确认技术路线可行，跑通"搜索→采集→存储"最小闭环

**任务**：
- [ ] 安装 Python 3.11+（brew install python@3.11）
- [ ] 安装 browser-use (`uv add "browser-use[core]"`)
- [ ] 安装 Scrapling (`pip install scrapling`)
- [ ] 配置本地 Chrome 远程调试（`chrome://inspect/#remote-debugging`）
- [ ] 编写第一个脚本：打开 BOSS直聘，搜索"Python工程师"，截图验证
- [ ] 用 Scrapling 解析页面，提取候选人基本信息

**验证标准**：
- 能从 BOSS直聘 打开搜索页面
- 能提取到候选人列表
- 能存储到 SQLite

### Phase 1: BOSS直聘 完整采集（1-2 周）

**目标**：能从 BOSS直聘 批量采集候选人数据到本地

**任务**：
- [ ] 实现 BOSS直聘 平台适配器（继承 MediaCrawler 的平台架构）
- [ ] 关键词搜索 → 翻页 → 逐个打开候选人主页
- [ ] 用 Scrapling 解析候选人页面，提取结构化数据
- [ ] 数据存储到 SQLite/PostgreSQL
- [ ] 反反爬处理：代理轮换 + 请求间隔 + CDP 复用登录态
- [ ] 去重：同一候选人只存一次
- [ ] 日志记录：成功/失败/被封

**输出**：
- 一个脚本，输入关键词，自动采集 BOSS直聘 候选人数据
- 本地数据库，包含结构化候选人信息

### Phase 2: 多平台扩展（2-3 周）

**目标**：覆盖 3-4 个平台，支持多源聚合

**任务**：
- [ ] 猎聘平台适配器
- [ ] 脉脉平台适配器
- [ ] GitHub 平台适配器（简单，先做）
- [ ] 多平台去重（同一个人出现在多个平台）
- [ ] 统一数据模型（不同平台数据格式统一）
- [ ] 搜索 Agent 调度（自动选平台、选策略）

### Phase 3: AI 分析 + 产品化（2-3 周）

**目标**：AI 自动评分，WebUI 展示

**任务**：
- [ ] LLM 集成：给 JD，自动给候选人打匹配分
- [ ] 技能提取：从简历中提取结构化技能
- [ ] WebUI（Gradio）：搜索框 + 结果表格 + 详情
- [ ] 导出功能：CSV/Excel
- [ ] 代理池管理
- [ ] 错误重试 + 异常处理
- [ ] 文档

---

## 六、关键技术方案

### 6.1 browser-use 在人才寻源中的应用

```python
from browser_use import Agent, Browser, Tools
from browser_use.beta import Agent as BetaAgent

# 搜索候选人
agent = Agent(
    task="搜索'Python工程师'，采集前10个候选人的姓名、公司、职位",
    llm=ChatBrowserUse(),
    browser=Browser(
        headless=True,  # 开发时用 False 调试
        allowed_domains=["www.zhipin.com", "www.liepin.com"],
    ),
)
history = await agent.run()
```

### 6.2 Scrapling 解析器

```python
from scrapling import DynamicFetcher

# 自适应解析，不怕平台改版
fetcher = DynamicFetcher()
response = fetcher.get("https://www.zhipin.com/job_detail/xxx")

# Scrapling 会自动处理页面结构变化
# 提取候选人信息
candidate = extract_candidate(response.html)
```

### 6.3 平台适配抽象

```python
class PlatformAdapter(ABC):
    """所有平台适配器的基类"""
    
    @abstractmethod
    def search(self, keyword: str, **kwargs) -> List[Candidate]:
        """关键词搜索"""
        pass
    
    @abstractmethod
    def get_candidate_detail(self, url: str) -> Candidate:
        """获取候选人详情页"""
        pass
    
    @abstractmethod
    def get_rate_limit(self) -> int:
        """获取请求间隔（秒）"""
        pass
    
    @abstractmethod
    def is_login_required(self) -> bool:
        """是否需要登录"""
        pass
```

### 6.4 反反爬策略矩阵

| 策略 | 适用场景 | 实现方式 |
|------|----------|----------|
| **CDP 模式** | 所有需要登录态的平台 | 复用本地 Chrome |
| **代理池** | 高频采集 | 住宅代理 + 数据center代理 |
| **请求间隔** | 所有平台 | 随机间隔 2-8 秒 |
| **User-Agent 轮换** | 所有平台 | 50+ UA 池 |
| **浏览器指纹** | 反反爬严格的平台 | browser-use stealth |
| **登录态缓存** | BOSS/猎聘/脉脉 | Cookie 持久化 |
| **CAPTCHA 处理** | 触发验证码时 | 人工确认 / 打码服务 |

---

## 七、与竞品对比

| 能力 | 本项目 | Pin | SeekOut | 100x.bot |
|------|--------|-----|---------|----------|
| 全职业覆盖 | ✅ 设计如此 | ✅ | ✅ | ✅ |
| 多源聚合 | ✅ 自建 | ✅ | ✅ | ✅ |
| 本地数据存储 | ✅ | ❌ 云端 | ❌ 云端 | ❌ 云端 |
| AI 分析 | ✅ LLM | ✅ | ✅ | ✅ |
| 开源 | ✅ | ❌ | ❌ | ❌ |
| 成本 | 低（仅LLM+代理） | 高（SaaS） | 高（SaaS） | 高（SaaS） |
| 数据主权 | 完全自有 | 云端 | 云端 | 云端 |
| 可定制 | ✅ | ❌ | ❌ | ❌ |
| 支持中文平台 | ✅ BOSS/猎聘/脉脉 | 一般 | 弱 | 一般 |

**核心优势**：
1. **数据完全本地化** — 候选人数据在自己手里，不依赖第三方
2. **中文平台全覆盖** — Pin/SeekOut 主要覆盖海外，本项目专攻国内
3. **成本低** — SaaS 年费几千到几万，本项目只需 LLM token + 代理费用
4. **可定制** — 想加什么平台、什么字段，自己说了算

---

## 八、成本估算（MVP 阶段）

| 项目 | 月度成本 |
|------|----------|
| LLM API（GPT-4/Claude） | ¥200-500 |
| 代理 IP | ¥100-300 |
| 服务器（可选，本地可跑） | ¥0 |
| **合计** | **¥300-800/月** |

---

## 九、风险与对策

### 9.1 法律合规风险
- **对策**：只采集公开可见的信息；不存储敏感信息（身份证号等）；用户授权后才采集；参考 MediaCrawler 免责声明
- **重点**：BOSS直聘等平台的 TOS 通常禁止爬虫，需注意频率控制

### 9.2 账号被封风险
- **对策**：CDP 模式复用登录态；代理轮换；模拟人工行为（随机间隔、随机滚动）；用备用号采集

### 9.3 平台改版导致失效
- **对策**：Scrapling 自适应解析；站点经验积累；监控采集成功率，低于阈值自动告警

### 9.4 反爬升级
- **对策**：browser-use stealth 模式；付费代理（住宅代理）；CAPTCHA 打码服务

### 9.5 数据质量问题
- **对策**：多源去重；LLM 自动校验；人工审核流程

---

## 十、技术栈总结

| 层级 | 技术 | 选型理由 |
|------|------|----------|
| **语言** | Python 3.11+ | 参考项目都是 Python |
| **浏览器自动化** | browser-use (Rust Core) | 当前最成熟的 AI 浏览器自动化，98K Star |
| **自适应解析** | Scrapling | 页面改版自动适应，抗维护成本 |
| **多平台适配** | 自研（MediaCrawler 架构） | 每个平台一个模块，统一接口 |
| **Agent 调度** | 自研（web-access 三层通道） | WebSearch → WebFetch → CDP Browser |
| **LLM** | OpenAI GPT-4 / Claude | 候选人分析 + 技能提取 + 匹配评分 |
| **数据存储** | SQLite (MVP) → PostgreSQL (生产) | 结构化候选人数据 |
| **向量搜索** | ChromaDB | 技能语义搜索 |
| **WebUI** | Gradio | 快速搭建，10行代码出界面 |
| **CLI** | click | 命令行工具 |
| **经验积累** | JSON 文件 | 按域名存储操作经验 |
| **部署** | 本地 macOS (MVP) → Docker (生产) | 先在本地验证，再容器化 |

---

## 十一、立即行动

1. **先装 Python 3.11+**（你的系统 Python 是 3.9，不够用）
2. **跑通 browser-use demo**（验证 CDP 模式能连接本地 Chrome）
3. **手动测试 BOSS直聘**（确认能打开、能搜索、能提取信息）
4. **设计数据库 schema**（确认存什么字段）
5. **实现第一个平台适配器**（BOSS直聘，全项目最关键）

---

*最后更新: 2026-06-11*
