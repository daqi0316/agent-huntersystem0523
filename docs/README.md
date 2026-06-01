# AI 招聘系统 — 文档索引

> 统一入口。所有根目录 Markdown 文档的快速跳转与简介。

---

## 一、需求与设计

| 文档 | 简介 | 维护者 |
|---|---|---|
| [AI_Recruitment_System_PRD.md](../AI_Recruitment_System_PRD.md) | 需求文档 (PRD) — 业务目标、功能清单、11 页面映射 | qixia |
| [AI_Recruitment_Multi_Agent_System_Prompt_Architecture.md](../AI_Recruitment_Multi_Agent_System_Prompt_Architecture.md) | 7 种 Agent 架构（单 Agent / Pipeline / Router / Aggregator / Orchestrator / Gen-Eval / Human-in-Loop）详细设计 | qixia |
| [agent.md](../agent.md) | 实施指南 — 三阶段路线（基础设施 / 流水线 / 商业化）| qixia |

## 二、Agent 提示词与记忆

| 文档 | 简介 |
|---|---|
| [Ai 招聘Agent 提示词系统.md](../Ai%20招聘Agent%20提示词系统.md) | 整套 Agent 提示词体系（系统级 / 任务级）|
| [简历解析_Agent_系统提示词_Prompt-H.md](../简历解析_Agent_系统提示词_Prompt-H.md) | 简历解析 Agent 的完整 Prompt-H（461 行参考实现，**生产用 T.1 精简版 80 行**）|
| [AI招聘Agent_上下文记忆架构设计.md](../AI招聘Agent_上下文记忆架构设计.md) | 上下文记忆架构（短期 / 长期 / 情景 / 语义）|
| [第八章 记忆与检索.md](../第八章%20记忆与检索.md) | 记忆系统：向量检索 + 关键词 + 关联图谱 |
| [第九章 上下文工程.md](../第九章%20上下文工程.md) | 上下文工程：压缩 / 摘要 / 注入策略 |

## 三、工具与编排

| 文档 | 简介 |
|---|---|
| [AI_招聘系统_MCP_工具系统设计文档_v2.md](../AI_招聘系统_MCP_工具系统设计文档_v2.md) | MCP 工具系统设计（**实施以 Phase T 为准**）|
| [LangGraph任务快照.md](../LangGraph任务快照.md) | LangGraph 任务快照与编排示例（**实施以 Phase S 为准**）|

## 四、实施路线

| 文档 | 状态 |
|---|---|
| [`.omo/plans/consolidated-next-plan.md`](../.omo/plans/consolidated-next-plan.md) | ⭐ **当前权威路线**（S / T / U 阶段）|
| [`.omo/plans/_archive/`](../.omo/plans/_archive/) | 历史 plan 归档（v1-v5 + multi-agent-orchestration + cover 文件）|

## 五、Session 状态

| 文件 | 用途 |
|---|---|
| [`.opencode/anchored-summary.md`](../.opencode/anchored-summary.md) | 跨 session 状态摘要（~80% 完成度）|
| [`.omo/anchor/anchor-summary.md`](../.omo/anchor/anchor-summary.md) | 最近 session 完成的工作 |
| [`.omo/summary.md`](../.omo/summary.md) | 上次 session 详细总结 |

---

## 阅读顺序建议

**新加入的工程师**：
1. PRD → 业务全景
2. 架构文档 → 7 种 Agent 模式
3. agent.md → 实施路线
4. consolidated-next-plan.md → 当前在做啥

**写新 Agent 的工程师**：
1. 架构文档（你的 Agent 属于哪种图）
2. 提示词系统 → 你的 Agent 的系统提示词模板
3. 简历解析 Prompt-H → 参考实现
4. 上下文工程 → 你的 Agent 怎么用上下文

**修 bug 的工程师**：
1. anchored-summary.md → 系统当前状态
2. .omo/anchor/ → 最近改了什么
3. 涉及的 Agent / Service 源码
