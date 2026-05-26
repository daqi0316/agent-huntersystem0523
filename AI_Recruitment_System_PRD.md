# AI 招聘助手 · 产品需求文档

> 版本：v2.2  
> 日期：2026-05-25  
> 作者：qixia  
> 状态：技术路线图 → 产品级 PRD

---

## 一、概述

### 1.1 目标用户

| 角色 | 场景 | 痛点 |
|:---|:---|:---|
| **招聘经理** | 每周处理 50+ 简历，需要快速筛选出 Top 10 | 手动筛选耗时 2-4 小时/次，标准不一致 |
| **HR 专员** | 协调面试安排，跨邮件/日历/候选人沟通 | 来回 5+ 封邮件才能定一个时间 |
| **招聘负责人** | 月度招聘复盘，分析渠道效率、OTD 周期 | 数据散落在 Excel 和邮件里，汇总一次要半天 |

### 1.2 核心指标

| 指标 | 当前（估算） | 目标 |
|:---|:---|:---|
| 单次初筛耗时 | 1 人 × 2-4 小时 | AI 辅助下 15 分钟完成 |
| 面试安排协调回合 | 5-8 封邮件 | 1 次 AI 建议 + 1 次确认 |
| 招聘复盘准备时间 | 半天手动汇总 | 看板实时可见，零准备 |
| JD 撰写时间 | 30-60 分钟 | AI 初稿 3 分钟 + 人工微调 5 分钟 |

### 1.3 关键约束

- 候选人数据不出域（本地推理优先，云端 API 做 fallback）
- 支持多 HR 成员协作（中期目标）
- 符合个保法对候选人数据的要求（删除权、导出权）

---

## 二、现有能力盘点

### 2.1 后端已实现

| 能力 | 状态 | 备注 |
|:---|:---|:---|
| 6 种 Agent 模式（Pipeline/Router/Aggregator/Orchestrator/GenEval/HumanLoop） | ✅ 全部实现 | 七图架构全部可运行 |
| AgentService ReAct 工具循环（11 内置工具 + 动态注册） | ✅ | 对话记忆、工具调用、工具可视化 |
| Pipeline 流水线初筛（JD 解析 → 向量检索 → 门控质检） | ✅ | Gate 机制完整 |
| Aggregator 多维度并行评估（技术/文化/潜力） | ✅ | 加权共识合并 |
| HumanLoop 审批流程（提案 → 确认/拒绝/过期清理） | ✅ | 面试安排场景 |
| LLM 双客户端（OMLX/vLLM，config 切换） | ✅ | 含重试 + 嵌入 |
| 动态技能系统（app/skills/ 自动发现，install_skill 运行时安装） | ✅ | 当前 2 技能（weather, web_search）|
| 存储层（PostgreSQL + Redis + Qdrant + Alembic） | ✅ | 完整 |
| 认证系统（JWT register/login/me + AuthGuard） | ✅ | 基础可用 |
| 测试套件（46 个测试通过，含参数化 + mock） | ✅ | 覆盖率 50% |

### 2.2 前端已实现

| 能力 | 状态 | 备注 |
|:---|:---|:---|
| 12 页面（Dashboard/Jobs/Candidates/Screening/Interview/Reports/Knowledge/Settings/Agent Chat/Evaluation/Talent Profile/JD Generator） | ✅ | 全部路由注册 |
| AI 对话界面（ReAct 风格 + 工具调用可视化 + 建议提示） | ✅ | 本地持久化 |
| 简历上传 + 提取 + 信息展示 | ✅ | Candidate 完整 CRUD |
| Recharts 图表（面积图/柱状图/饼图/漏斗图） | ✅ | Dashboard + Reports |
| shadcn/ui 组件库 + 可折叠侧边栏 + AuthGuard | ✅ | 一致风格 |
| Zustand 状态管理 + localStorage | ✅ | |

### 2.3 实际 vs 规划对比

| 原 PRD 规划项 | 实际 | 差异 |
|:---|:---|:---|
| tRPC 端到端类型安全 | 直接 fetch | 可接受先不迁移 |
| vLLM GPU 集群 | OMLX 客户端已实现，未部署 GPU | 无 GPU 时暂缓 |
| RabbitMQ / MinIO / Traefik / Sentry | 未实现 | 商业化前不需要 |
| SSE 实时推送 | 未标准化 | Phase 1 补充 |
| 七图 Agent 模式 | **全部已实现**（不是规划中） | 重大利好 |

---

## 三、已知问题（需修复后进入 Phase 1）

| 问题 | 影响 | 严重程度 |
|:---|:---|:---|
| RouterAgent 是 stub，全局意图路由未运作 | 前端 Router 页面无实际分类能力 | 🔴 |
| 前端 API 错误处理不一致（有时弹 Toast，有时静默失败） | 用户体验差，故障难排查 | 🔴 |
| 后端统一错误响应格式未完整推广 | 前端难以统一处理错误展示 | 🟡 |
| 测试覆盖率 50% | 后续重构无保护网 | 🟡 |
| CI 中没有安全扫描 | 合入密钥到代码的风险 | 🟡 |
| 无 SSE 推送标准化 | Pipeline 执行进度对用户不可见 | 🟡 |

---

## 四、演进路线

### Phase 1：数据流闭环（2 周）

**单一目标**：候选人在系统中的全链路能从「导入」跑到「面试安排」。

```
入 口：简历上传 / 手动创建
    ↓
简历提取：ResumeExtractor 结构化
    ↓
AI 初筛：PipelineAgent + AggregatorAgent
    ↓
评估报告：Evaluation CRUD 写库
    ↓
面试安排：HumanLoopAgent 生成提案
    ↓
确认执行：前端确认界面 → 状态更新
```

**具体任务**：

| 任务 | 工作量 | 说明 |
|:---|:---|:---|
| 串联 Candidate → Pipeline → Evaluation → Interview 数据流 | 2-3 天 | 缺边界检查、状态机、异常处理 |
| Pipeline SSE 进度推送 | 1 天 | 前端 Step Indicator 展示 Gate 状态 |
| HumanLoop UI 确认界面 | 2 天 | 面试安排提案 → 确认 → 发送 |
| 统一后端错误响应格式 | 1 天 | `{success, data/error}` 全局一致性 |
| 前端统一错误处理 | 1 天 | ErrorBoundary + Toast 全局 |
| 补全 Pipeline/Aggregator 单元测试 | 2 天 | 关键路径 80%+ 覆盖率 |
| CI 引入安全扫描（git-secrets + ruff check） | 0.5 天 | 防止密钥合入 |

**退出标准**（必须全部满足）：
- [ ] 自动化 E2E 测试覆盖「上传简历 → 初筛 → 出报告 → 安排面试」全链路
- [ ] 全链路端到端手动走通一次，无静默失败
- [ ] 所有 API 返回统一格式
- [ ] Pipeline 进度通过 SSE 推送到前端并展示
- [ ] CI 中测试通过 + 安全扫描无告警

---

### Phase 2a：跨会话记忆（3 周）

**目标**：Agent 能记住跨会话的用户偏好和历史筛选模式。

**方案**：PostgreSQL 全文索引（非 FTS5 文件系统，架构更匹配）。

```
schemas:
  session_summaries
    ├── session_id (UUID PK)
    ├── user_id (FK → users)
    ├── summary_text (TEXT, FTS indexed)
    ├── key_insights (JSONB)
    │   ├── preferred_skills: string[]
    │   ├── salary_range: {min, max}
    │   ├── screening_patterns: {filters, weights}
    │   └── rejected_reasons: string[]
    ├── created_at TIMESTAMPTZ
    └── updated_at TIMESTAMPTZ
```

**关键设计决策**：
- 每次 Agent 会话结束时自动生成摘要（LLM 从 messages 中提取关键洞察）
- 新会话开始时自动加载相关历史摘要（向量相似度 + 关键词匹配混合检索）
- 用户可手动标记"保留此经验"或"删除不准确记忆"
- 不引入新基础设施，完全在 PostgreSQL 内完成

**退出标准**：
- [ ] 会话结束后自动生成结构化摘要并写入 session_summaries
- [ ] 新会话加载相关历史摘要并在 Agent prompt 中注入
- [ ] 用户可查看/编辑/删除已存储的记忆
- [ ] 连接候选人的跨会话画像（同一候选人在多次初筛中的评分变化）

---

### Phase 2b：技能演化（4 周）

**目标**：Agent 能从成功的初筛/评估流程中自动提取可复用技能，注册到 skill 系统。

```
成功流程记录
    ↓
LLM 分析：哪些步骤、哪些判断标准、哪些工具调用模式
    ↓
生成 Skill 模板（name + description + tools + handlers）
    ↓
写入 app/skills/*/（动态注册）
    ↓
新会话中自动加载匹配 Skill
```

**实现要点**：
- 不追求完美提取；首次准确率 > 60% 即算可用，人工微调即可
- 每个提取的 Skill 附带置信度分数，置信度 > 0.8 可自动注册，< 0.8 需人工确认
- 与 Phase 2a 记忆层共享 session_summaries 数据源

**退出标准**：
- [ ] 从 3+ 次成功初筛流程中提取出可复用 Skill
- [ ] 提取的 Skill 在后续会话中生效（不降低初筛质量）
- [ ] 置信度机制运行正确（高置信度自动注册，低置信度提示人工确认）

---

### Phase 3：招聘助手智能化（4 周）

| 功能 | 说明 | 优先级 |
|:---|:---|:---|
| 主动式候选人推荐 | 基于历史筛选模式，新简历上传后自动推荐 Top 5 | P1 |
| 多轮对话式初筛 | Agent 追问候选人细节而非一次出分 | P1 |
| 邮件/日历 MCP 集成 | HumanLoop 确认后自动发送邮件、预约日历 | P1 |
| 面试问题智能生成 | 根据 JD + 候选人简历生成定制面试题 | P2 |
| 候选人全生命周期视图 | 从投递到入职的时间线 + 状态变化 | P2 |

---

### Phase 4：商用化（4 周）

| 能力 | 说明 |
|:---|:---|
| 多租户 + RBAC | Schema-per-tenant 隔离 + 角色权限 |
| 合规 | 候选人数据导出/删除/脱敏（GDPR/个保法） |
| 计费 | 用量计量 + Stripe 集成 |
| 部署 | Docker Compose 生产配置 + CI/CD + 监控 |

---

## 五、非功能性要求

### 5.1 安全

| 要求 | 优先级 |
|:---|:---|
| 所有 API 端点需认证（public 端点白名单） | Phase 1 |
| 密钥/Token 仅存环境变量，零硬编码 | Phase 1 |
| 候选人数据支持物理删除 | Phase 1 |
| SQL 注入防护（已有 SQLAlchemy 参数化，确认无 raw SQL） | Phase 1 |
| 前端展示候选人时自动脱敏（电话/邮箱部分隐藏） | Phase 3 |
| 敏感操作审计日志 | Phase 4 |

### 5.2 性能

| 场景 | 目标 |
|:---|:---|
| 单次 AI 初筛（JD 解析 + 检索 + 评估） | < 30 秒（含 LLM 推理） |
| 前端页面加载 | < 2 秒首屏 |
| SSE 事件延迟 | < 1 秒 |
| 数据库查询（列表页） | < 200ms |

### 5.3 可靠性

| 场景 | 策略 |
|:---|:---|
| LLM 调用失败 | 自动重试 3 次（已有），仍然失败 → 返回清晰错误提示，不阻塞操作 |
| Vector DB 不可用 | 回退到 PostgreSQL ILIKE / tsvector 关键词搜索 |
| Redis 不可用 | 降级为无缓存模式，不影响核心功能 |

---

## 六、不做清单

明确本期不做的功能，缩小聚焦范围：

| 功能 | 原因 | 可能时机 |
|:---|:---|:---|
| 多消息平台（微信/邮件/短信） | 招聘核心在 Web 端，消息推送单一 | Phase 4 后 |
| 子 Agent 预算控制 | 当前无多 Agent 并行竞态问题 | 不预测 |
| 行为画像建模 | 成熟度低，Hermes 自己也还是实验性 | 不预测 |
| ATS 双向同步（Greenhouse/Lever） | 集成成本高，先做人机界面 | 商业化后按需 |
| 移动端 App | Web 优先，PWA 备选 | Phase 4 后 |

---

## 七、风险清单

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:---|:---|:---|
| 本地 LLM（OMLX）推理速度不足 | 中 | 初筛 > 60 秒不可接受 | 保持 OMLX/vLLM 双模式，可切云端 API |
| 向量检索召回率偏低 | 中 | 候选人不匹配 | 混合检索（向量 + PostgreSQL FTS 关键词） |
| 技能提取质量低，用户不信任 | 高 | 技能演化功能无用 | 设置信度门槛 + 手动确认流程 |
| 跨会话记忆污染 | 中 | 错误记忆影响后续判断 | 用户可审查/删除/标记不准确 |
| 多租户数据隔离泄露 | 低 | 合规事故 | Schema-per-tenant + 独立连接池 |

---

## 八、优先级矩阵

```
                   高价值
                    │
        Phase 2b   │  Phase 3
        技能演化    │  主动推荐
        ★★★☆☆     │  ★★★★☆
                    │
  ──────────────高难度┼──────────── 低难度
                    │
        Phase 1    │  Phase 2a
        数据流闭环  │  跨会话记忆
        ★★★★☆     │  ★★★☆☆
                    │
                   低价值
```

建议执行顺序：Phase 1 → Phase 2a → Phase 2b → Phase 3 → Phase 4

---

*本文档基于实际代码库分析编写。与 v2.1 的关键变化：增加了用户画像/指标/约束、修正了测试数据、重组了 Phase 并加退出标准、补充了安全/可靠性/不做清单。*
