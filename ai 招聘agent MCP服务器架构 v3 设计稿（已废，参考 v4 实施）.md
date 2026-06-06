# AI 招聘系统 MCP 工具系统设计文档（精简版）

> **版本**: v2.0  
> **日期**: 2026-05-31  
> **设计原则**: 每个 Agent 3-5 个工具，一个工具对应一个核心业务能力  
> **产品形态**: AI 独立驾驶 + 人机共驾

---

## 目录

1. [系统概述](#1-系统概述)
2. [架构总览](#2-架构总览)
3. [Agent 编排](#3-agent-编排)
4. [MCP 工具清单](#4-mcp-工具清单)
5. [简历解析 Agent](#5-简历解析-agent)
6. [寻访 Agent](#6-寻访-agent)
7. [筛选 Agent](#7-筛选-agent)
8. [面试协调 Agent](#8-面试协调-agent)
9. [薪酬谈判 Agent](#9-薪酬谈判-agent)
10. [入职跟进 Agent](#10-入职跟进-agent)
11. [数据分析 Agent](#11-数据分析-agent)
12. [共享层工具](#12-共享层工具)
13. [权限矩阵](#13-权限矩阵)
14. [实施路线图](#14-实施路线图)
15. [附录](#15-附录)

---

## 1. 系统概述

### 1.1 设计目标

AI-Native 招聘管理系统，用户通过自然语言对话完成招聘全流程，复杂场景保留人工确认入口。

### 1.2 核心原则

| 原则 | 说明 |
|------|------|
| **Agent 专属** | 每个 Agent 3-5 个工具，只暴露职责相关的业务能力 |
| **工具即 API** | 一个工具 = 一个核心业务能力，不拆分过细 |
| **合并同类项** | 提取/解析/评估合并为统一入口 |
| **共享收敛** | 只保留真正通用的跨 Agent 能力 |
| **Human-in-the-loop** | 敏感操作必须人工确认 |
| **操作可追溯** | 所有调用记录审计日志 |

### 1.3 技术栈

| 层级 | 选型 |
|------|------|
| MCP Server | `@modelcontextprotocol/sdk` |
| 传输 | SSE / stdio |
| 认证 | OAuth 2.1 / API Key |
| Agent 编排 | LangGraph |
| 业务 API | RESTful API |
| 数据库 | PostgreSQL |

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                         用户交互层                           │
│  ┌─────────────┐      ┌─────────────┐                     │
│  │ AI 对话入口  │      │ 管理后台界面  │                     │
│  │ (默认路径)   │      │ (隐藏/兜底)   │                     │
│  └──────┬──────┘      └──────┬──────┘                     │
│         └──────────┬──────────┘                            │
│                    ↓                                        │
│         ┌─────────────────────┐                             │
│         │   编排层 (Orchestrator)  │                        │
│         │  意图识别 / Agent 路由 / 结果聚合  │               │
│         └──────────┬──────────┘                            │
│                    ↓                                        │
│  ┌────────┬────────┬────────┬────────┬────────┬────────┐  │
│  │简历解析 │  寻访  │  筛选  │ 面试   │ 薪酬   │ 入职   │  │
│  │  Agent │ Agent  │ Agent  │ 协调   │ 谈判   │ 跟进   │  │
│  │  3工具  │ 3工具  │ 3工具  │ Agent  │ Agent  │ Agent  │  │
│  │        │        │        │ 4工具  │ 3工具  │ 3工具  │  │
│  └────────┴────────┴────────┴────────┴────────┴────────┘  │
│                    ↓                                        │
│         ┌─────────────────────┐                             │
│         │   共享层 (4 个工具)   │                             │
│         │ 记忆 / 知识 / 通知 / 权限  │                        │
│         └──────────┬──────────┘                            │
│                    ↓                                        │
│         ┌─────────────────────┐                             │
│         │   MCP Server          │                             │
│         └──────────┬──────────┘                            │
│                    ↓                                        │
│         ┌─────────────────────┐                             │
│         │   业务系统 API + 数据库  │                        │
│         └─────────────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 数据流

1. 用户输入 → 编排层意图识别
2. 路由到对应 Agent
3. Agent 调用专属/共享工具
4. MCP Server 转换为业务 API
5. 业务系统执行，返回结果
6. Agent 整合，编排层生成回复

---

## 3. Agent 编排

### 3.1 编排层职责

- 意图分类：简历解析 / 寻访 / 筛选 / 面试 / 薪酬 / 入职 / 数据分析 / 通用查询
- 上下文保持：跨轮对话的任务状态跟踪
- 异常处理：Agent 失败时的降级策略
- 人机切换：复杂场景引导至管理界面

### 3.2 Agent 间协作流程

```
用户: "帮我招一个 5 年 Java 经验的后端"
  ↓
[编排层] → 路由到寻访 Agent
  ↓
[寻访 Agent] publish_job(发布职位) + search_candidates(搜索人才库)
  ↓
收到简历 → [简历解析 Agent] parse_resume(解析)
  ↓
结构化数据 → [筛选 Agent] match_candidate(匹配度分析) + screen_candidate(初筛)
  ↓
通过 → [面试协调 Agent] schedule_interview(安排面试)
  ↓
面试通过 → [薪酬谈判 Agent] analyze_salary(薪资分析) + create_offer(生成 Offer)
  ↓
Offer 接受 → [入职跟进 Agent] get_onboarding_plan(入职计划)
  ↓
全程 → [数据分析 Agent] get_dashboard(数据看板)
```

---

## 4. MCP 工具清单

### 4.1 统计

| Agent | 专属工具 | 共享工具 | 合计 |
|-------|---------|---------|------|
| 简历解析 | 3 | 4 | 7 |
| 寻访 | 3 | 4 | 7 |
| 筛选 | 3 | 4 | 7 |
| 面试协调 | 4 | 4 | 8 |
| 薪酬谈判 | 3 | 4 | 7 |
| 入职跟进 | 3 | 4 | 7 |
| 数据分析 | 3 | 4 | 7 |
| **总计** | **22** | **4** | **26** |

### 4.2 命名规范

```
{动词}_{名词}

示例:
  parse_resume          解析简历
  search_candidates     搜索候选人
  schedule_interview    安排面试
  create_offer          创建 Offer
  get_dashboard         获取仪表盘
```

### 4.3 通用返回结构

```typescript
interface MCPResponse<T> {
  status: "success" | "partial" | "failed" | "pending_confirmation";
  data?: T;
  error?: {
    code: string;
    message: string;
    retryable: boolean;
  };
  confirmation?: {
    required: boolean;
    token: string;
    preview: any;
    message: string;
  };
  meta: {
    request_id: string;
    timestamp: string;
    agent: string;
    tool: string;
  };
}
```

---

## 5. 简历解析 Agent

> **Prompt-H** | 职责：简历 → 结构化数据

### 5.1 工具列表

| 工具 | 功能 | 输入 | 输出 | 权限 |
|------|------|------|------|------|
| `parse_resume` | 解析单份简历 | 文件/文本/URL | 结构化数据 + 质量评分 + 风险标记 | 🟢 |
| `batch_parse_resumes` | 批量解析 | 文件列表 | 批量结果 + 失败列表 | 🟢 |
| `get_candidate_profile` | 获取候选人画像 | candidate_id | 聚合后的完整档案 | 🟢 |

### 5.2 `parse_resume` 详细定义

**输入参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | ✅ | `upload` / `email` / `job_board` / `linkedin` |
| `content` | string | ❌ | 简历文本（文本格式时必填） |
| `file_url` | string | ❌ | 文件 URL（文件格式时必填） |
| `file_type` | string | ❌ | `pdf` / `doc` / `docx` / `jpg` / `png` |
| `target_job_id` | string | ❌ | 关联职位 ID |

**返回结构**:

```json
{
  "status": "success",
  "data": {
    "candidate_id": "cand_001",
    "basic_info": {
      "name": "张三",
      "phone": "138****8888",
      "email": "zhangsan@example.com",
      "city": "北京",
      "current_company": "字节跳动",
      "current_title": "高级后端工程师",
      "years_of_experience": 5
    },
    "work_experience": [
      {
        "company": "字节跳动",
        "title": "高级后端工程师",
        "period": "2022.03 - 至今",
        "highlights": ["QPS 提升 300%", "系统可用性 99.99%"]
      }
    ],
    "education": [
      {
        "school": "清华大学",
        "major": "计算机科学与技术",
        "degree": "本科"
      }
    ],
    "skills": ["Java", "Spring Boot", "Redis", "Kafka"],
    "match_tags": ["大厂背景", "高并发经验", "技术负责人"],
    "quality_score": 82,
    "red_flags": ["3年2跳"],
    "is_duplicate": false,
    "parsed_at": "2025-05-31T14:00:00Z"
  },
  "meta": {
    "request_id": "req_001",
    "timestamp": "2025-05-31T14:00:00Z",
    "agent": "resume_parser",
    "tool": "parse_resume"
  }
}
```

**错误处理**:

| 错误码 | 场景 | 处理 |
|--------|------|------|
| `FILE_CORRUPTED` | 文件损坏 | 提示重新上传 |
| `LOW_CONFIDENCE` | 置信度 < 0.6 | 标记"需人工复核" |
| `UNSUPPORTED_FORMAT` | 格式不支持 | 提示支持的格式 |

---

## 6. 寻访 Agent

> **Prompt-B** | 职责：找人 + 发布职位

### 6.1 工具列表

| 工具 | 功能 | 输入 | 输出 | 权限 |
|------|------|------|------|------|
| `search_candidates` | 搜索候选人 | 技能、经验、地点、来源 | 候选人列表 | 🟢 |
| `publish_job` | 发布职位 | job_id、渠道、内容 | 发布状态 | 🟡 |
| `add_candidate` | 添加候选人 | 候选人信息 | 入库结果 | 🟡 |

### 6.2 `search_candidates` 详细定义

**输入参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `skills` | string[] | ❌ | 技能关键词 |
| `experience_min` | number | ❌ | 最低年限 |
| `experience_max` | number | ❌ | 最高年限 |
| `location` | string | ❌ | 工作地点 |
| `source` | string | ❌ | `internal` / `boss` / `linkedin` / `all` |
| `limit` | number | ❌ | 返回数量，默认 10 |

**返回结构**:

```json
{
  "status": "success",
  "data": {
    "total": 156,
    "candidates": [
      {
        "id": "cand_001",
        "name": "张三",
        "match_score": 92,
        "skills": ["Java", "Spring Boot"],
        "experience_years": 5,
        "current_company": "字节跳动",
        "location": "北京",
        "source": "internal",
        "last_contact": "2025-04-15"
      }
    ]
  }
}
```

---

## 7. 筛选 Agent

> **Prompt-C** | 职责：评估匹配度，决定通过/待定/拒绝

### 7.1 工具列表

| 工具 | 功能 | 输入 | 输出 | 权限 |
|------|------|------|------|------|
| `match_candidate` | 匹配度分析 | candidate_id, job_id | 匹配度报告 | 🟢 |
| `screen_candidate` | 执行初筛 | candidate_id, job_id, decision | 初筛结果 | 🟡 |
| `get_screening_queue` | 获取待筛选队列 | job_id, limit | 候选人列表 | 🟢 |

### 7.2 `match_candidate` 详细定义

**输入参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `candidate_id` | string | ✅ | 候选人 ID |
| `job_id` | string | ✅ | 职位 ID |

**返回结构**:

```json
{
  "status": "success",
  "data": {
    "match_score": 87,
    "skill_match": {
      "matched": ["Java", "Spring Boot", "MySQL"],
      "missing": ["Kubernetes"],
      "extra": ["Redis", "Kafka"]
    },
    "experience_match": {
      "required_years": 5,
      "actual_years": 5,
      "level_match": true
    },
    "salary_match": {
      "expected": "40k-60k",
      "budget": "35k-55k",
      "fit": "partial"
    },
    "overall_assessment": "技能匹配度高，经验符合，薪资略有超出，建议面试",
    "recommendation": "pass"
  }
}
```

---

## 8. 面试协调 Agent

> **Prompt-D** | 职责：安排面试、收集反馈

### 8.1 工具列表

| 工具 | 功能 | 输入 | 输出 | 权限 |
|------|------|------|------|------|
| `schedule_interview` | 安排/改期/取消面试 | candidate_id, time, interviewers, action | 面试 ID | 🔴 |
| `send_interview_invite` | 发送面试邀请 | interview_id, template | 发送状态 | 🔴 |
| `record_feedback` | 记录面试反馈 | interview_id, score, evaluation | 记录结果 | 🟡 |
| `get_interview_schedule` | 查看面试日程 | date_range, interviewer_id | 日程列表 | 🟢 |

### 8.2 `schedule_interview` 详细定义

**输入参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | ✅ | `schedule` / `reschedule` / `cancel` |
| `candidate_id` | string | ✅ | 候选人 ID |
| `interviewers` | string[] | ✅ | 面试官 ID 列表 |
| `time` | string | ✅ | 面试时间（ISO 8601） |
| `type` | string | ❌ | `phone` / `video` / `onsite`，默认 `video` |
| `duration_minutes` | number | ❌ | 时长，默认 60 |
| `reason` | string | ❌ | 改期/取消原因 |

**返回结构（需确认时）**:

```json
{
  "status": "pending_confirmation",
  "confirmation": {
    "required": true,
    "token": "cfm_001",
    "preview": {
      "candidate": "张三",
      "interviewers": ["李四（技术总监）"],
      "time": "2025-06-03T14:00:00+08:00",
      "type": "video",
      "duration": "60分钟"
    },
    "message": "请确认面试安排：6月3日 14:00，面试官李四，视频面试",
    "expires_at": "2025-05-31T15:00:00Z"
  }
}
```

---

## 9. 薪酬谈判 Agent

> **Prompt-E** | 职责：定薪、生成 Offer、跟踪

### 9.1 工具列表

| 工具 | 功能 | 输入 | 输出 | 权限 |
|------|------|------|------|------|
| `analyze_salary` | 薪资分析 | candidate_id, job_id | 薪资建议报告 | 🟢 |
| `create_offer` | 生成 Offer 包 | candidate_id, job_id, salary | Offer 详情 | 🔴 |
| `track_offer` | 跟踪 Offer 状态 | offer_id | 当前状态 | 🟢 |

### 9.2 `create_offer` 详细定义

**输入参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `candidate_id` | string | ✅ | 候选人 ID |
| `job_id` | string | ✅ | 职位 ID |
| `base_salary` | number | ✅ | 基本月薪 |
| `bonus_months` | number | ❌ | 年终奖月数，默认 2 |
| `equity` | object | ❌ | 期权/股权配置 |
| `benefits` | string[] | ❌ | 额外福利 |

**返回结构（需确认时）**:

```json
{
  "status": "pending_confirmation",
  "confirmation": {
    "required": true,
    "token": "cfm_002",
    "preview": {
      "candidate": "张三",
      "position": "高级后端工程师",
      "total_compensation": {
        "base": "45k/月",
        "annual_bonus": "90k",
        "equity": "10,000 股",
        "total_annual": "63 万"
      },
      "valid_until": "2025-06-15"
    },
    "message": "请确认 Offer 内容：年薪总包 63 万，有效期至 6 月 15 日"
  }
}
```

---

## 10. 入职跟进 Agent

> **Prompt-F** | 职责：入职准备、试用期管理

### 10.1 工具列表

| 工具 | 功能 | 输入 | 输出 | 权限 |
|------|------|------|------|------|
| `get_onboarding_plan` | 获取入职计划 | candidate_id | 入职任务清单 | 🟢 |
| `update_onboarding_progress` | 更新入职进度 | candidate_id, task_id, status | 更新结果 | 🟡 |
| `get_probation_status` | 获取试用期状态 | employee_id | 试用期评估 | 🟢 |

### 10.2 `get_onboarding_plan` 详细定义

**返回结构**:

```json
{
  "status": "success",
  "data": {
    "candidate_id": "cand_001",
    "employee_id": "emp_001",
    "onboarding_tasks": [
      { "id": "task_1", "name": "提交入职材料", "status": "completed", "deadline": "2025-06-01" },
      { "id": "task_2", "name": "签署劳动合同", "status": "pending", "deadline": "2025-06-03" },
      { "id": "task_3", "name": "IT 设备配置", "status": "pending", "deadline": "2025-06-05" },
      { "id": "task_4", "name": "导师分配", "status": "pending", "deadline": "2025-06-05" },
      { "id": "task_5", "name": "入职培训", "status": "pending", "deadline": "2025-06-10" }
    ],
    "progress": "20%",
    "start_date": "2025-06-09",
    "buddy": null
  }
}
```

---

## 11. 数据分析 Agent

> **Prompt-G** | 职责：看数据、出报告、给建议

### 11.1 工具列表

| 工具 | 功能 | 输入 | 输出 | 权限 |
|------|------|------|------|------|
| `get_dashboard` | 获取招聘仪表盘 | time_range, filters | 核心指标 | 🟢 |
| `get_pipeline_report` | 获取漏斗报告 | job_id / department | 各阶段转化 | 🟢 |
| `ask_analytics` | 自然语言问数据 | question | 数据答案 | 🟢 |

### 11.2 `ask_analytics` 详细定义

**输入参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | ✅ | 自然语言问题 |

**示例**:

```json
// 输入
{ "question": "这个月 Java 岗位的平均招聘周期多长？" }

// 输出
{
  "status": "success",
  "data": {
    "question": "这个月 Java 岗位的平均招聘周期多长？",
    "answer": "32 天",
    "breakdown": {
      "sourcing": 8,
      "screening": 5,
      "interview": 12,
      "offer": 5,
      "onboarding": 2
    },
    "trend": "比上月缩短 5 天",
    "benchmark": "行业平均 45 天"
  }
}
```

---

## 12. 共享层工具

> 所有 Agent 均可调用

| 工具 | 功能 | 输入 | 输出 | 权限 |
|------|------|------|------|------|
| `remember` | 记忆读写 | action, key, value | 存储/读取结果 | 🟢 |
| `ask_knowledge` | 知识查询 | question | 知识条目 | 🟢 |
| `notify` | 发送通知 | to, content, channel | 发送状态 | 🟡 |
| `check_permission` | 权限校验 | operation, resource | 是否有权限 | 🟢 |

### 12.1 `remember` 详细定义

**输入参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | ✅ | `save` / `get` / `update` / `delete` |
| `key` | string | ✅ | 记忆键 |
| `value` | any | ❌ | 记忆值（save/update 时必填） |
| `scope` | string | ❌ | `session` / `user` / `global`，默认 `session` |

**示例**:

```json
// 保存
{ "action": "save", "key": "current_job_id", "value": "job_001" }

// 读取
{ "action": "get", "key": "current_job_id" }
// 返回: { "value": "job_001", "created_at": "2025-05-31T14:00:00Z" }
```

### 12.2 `ask_knowledge` 详细定义

**示例**:

```json
// 输入
{ "question": "公司的年假政策是什么？" }

// 输出
{
  "answer": "入职满 1 年享 5 天年假，满 3 年享 10 天，满 5 年享 15 天",
  "source": "员工手册 v3.2",
  "confidence": 0.95
}
```

---

## 13. 权限矩阵

### 13.1 分级说明

| 标识 | 级别 | 说明 |
|------|------|------|
| 🟢 | 直接执行 | 查询类操作，无需确认 |
| 🟡 | 展示确认 | 创建/更新类操作，展示结果后自动执行 |
| 🔴 | 必须确认 | 敏感操作，用户明确确认后才执行 |
| ⛔ | 禁止 | AI 不可执行，必须人工操作 |

### 13.2 完整矩阵

| Agent | 工具 | 权限 | 确认内容 |
|-------|------|------|---------|
| 简历解析 | `parse_resume` | 🟢 | - |
| 简历解析 | `batch_parse_resumes` | 🟢 | - |
| 简历解析 | `get_candidate_profile` | 🟢 | - |
| 寻访 | `search_candidates` | 🟢 | - |
| 寻访 | `publish_job` | 🟡 | 展示发布渠道和内容 |
| 寻访 | `add_candidate` | 🟡 | 展示候选人信息 |
| 筛选 | `match_candidate` | 🟢 | - |
| 筛选 | `screen_candidate` | 🟡 | 展示通过/待定/决定及原因 |
| 筛选 | `get_screening_queue` | 🟢 | - |
| 面试协调 | `schedule_interview` | 🔴 | 时间、面试官、候选人、类型 |
| 面试协调 | `send_interview_invite` | 🔴 | 邮件预览 |
| 面试协调 | `record_feedback` | 🟡 | 展示评分和评价 |
| 面试协调 | `get_interview_schedule` | 🟢 | - |
| 薪酬谈判 | `analyze_salary` | 🟢 | - |
| 薪酬谈判 | `create_offer` | 🔴 | Offer 包详情（薪资、福利、有效期） |
| 薪酬谈判 | `track_offer` | 🟢 | - |
| 入职跟进 | `get_onboarding_plan` | 🟢 | - |
| 入职跟进 | `update_onboarding_progress` | 🟡 | 展示任务和状态变更 |
| 入职跟进 | `get_probation_status` | 🟢 | - |
| 数据分析 | `get_dashboard` | 🟢 | - |
| 数据分析 | `get_pipeline_report` | 🟢 | - |
| 数据分析 | `ask_analytics` | 🟢 | - |
| 共享层 | `remember` | 🟢 | - |
| 共享层 | `ask_knowledge` | 🟢 | - |
| 共享层 | `notify` | 🟡 | 展示通知内容和接收人 |
| 共享层 | `check_permission` | 🟢 | - |

### 13.3 禁止操作

| 操作 | 原因 | 替代方案 |
|------|------|---------|
| 删除候选人 | 数据不可恢复 | 标记为"已归档" |
| 删除职位 | 影响关联数据 | 关闭职位 |
| 修改薪资超预算 | 财务风险 | 走审批流程后人工操作 |
| 发送正式合同 | 法律效力 | 生成后人工审核发送 |

---

## 14. 实施路线图

### Phase 1：核心链路（第 1-2 周）

**目标**：简历解析 → 寻访 → 筛选 → 面试

```
简历解析 Agent:
  └── parse_resume

寻访 Agent:
  ├── search_candidates
  └── publish_job

筛选 Agent:
  ├── match_candidate
  └── screen_candidate

面试协调 Agent:
  ├── schedule_interview
  └── get_interview_schedule

共享层:
  ├── remember
  └── ask_knowledge
```

### Phase 2：效率提升（第 3-4 周）

**目标**：批量处理、薪酬、入职

```
新增:
  简历解析: batch_parse_resumes, get_candidate_profile
  寻访: add_candidate
  筛选: get_screening_queue
  面试协调: send_interview_invite, record_feedback
  薪酬谈判: analyze_salary, create_offer, track_offer
  入职跟进: get_onboarding_plan, update_onboarding_progress, get_probation_status
  共享层: notify, check_permission
```

### Phase 3：数据驱动（第 5-6 周）

**目标**：数据分析、自然语言查询

```
新增:
  数据分析: get_dashboard, get_pipeline_report, ask_analytics
```

---

## 15. 附录

### 15.1 MCP Server 最小实现

```typescript
// server.ts
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server(
  { name: "ai-recruitment-mcp", version: "2.0.0" },
  { capabilities: { tools: {} } }
);

// 工具注册表
const tools = {
  // 简历解析
  parse_resume: { /* schema */ },
  batch_parse_resumes: { /* schema */ },
  get_candidate_profile: { /* schema */ },

  // 寻访
  search_candidates: { /* schema */ },
  publish_job: { /* schema */ },
  add_candidate: { /* schema */ },

  // 筛选
  match_candidate: { /* schema */ },
  screen_candidate: { /* schema */ },
  get_screening_queue: { /* schema */ },

  // 面试协调
  schedule_interview: { /* schema */ },
  send_interview_invite: { /* schema */ },
  record_feedback: { /* schema */ },
  get_interview_schedule: { /* schema */ },

  // 薪酬谈判
  analyze_salary: { /* schema */ },
  create_offer: { /* schema */ },
  track_offer: { /* schema */ },

  // 入职跟进
  get_onboarding_plan: { /* schema */ },
  update_onboarding_progress: { /* schema */ },
  get_probation_status: { /* schema */ },

  // 数据分析
  get_dashboard: { /* schema */ },
  get_pipeline_report: { /* schema */ },
  ask_analytics: { /* schema */ },

  // 共享层
  remember: { /* schema */ },
  ask_knowledge: { /* schema */ },
  notify: { /* schema */ },
  check_permission: { /* schema */ }
};

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: Object.entries(tools).map(([name, tool]) => ({
    name,
    description: tool.description,
    inputSchema: tool.inputSchema
  }))
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  // 权限校验
  const perm = await checkPermission(name, args);
  if (!perm.allowed) {
    return errorResponse("PERMISSION_DENIED", perm.reason);
  }

  // 敏感操作确认
  if (perm.requiresConfirmation) {
    return confirmResponse(name, args);
  }

  // 执行
  const result = await executeTool(name, args);
  await logAudit(name, args, result);

  return successResponse(result);
});

const transport = new StdioServerTransport();
await server.connect(transport);
```

### 15.2 工具开发检查清单

- [ ] 描述清晰，AI 能正确选择
- [ ] 参数完整，必填/选填明确
- [ ] 返回 AI 友好，关键信息在前
- [ ] 权限明确，符合分级策略
- [ ] 错误处理完善，有重试建议
- [ ] 操作可追溯，记录审计日志
- [ ] 响应时间 < 3 秒
- [ ] 重复调用幂等

### 15.3 术语表

| 术语 | 说明 |
|------|------|
| MCP | Model Context Protocol，AI 与外部工具的标准通信协议 |
| Agent | 智能体，具备特定职责的 AI 实体 |
| Orchestrator | 编排层，负责意图识别和 Agent 路由 |
| Human-in-the-loop | 人机协同，敏感操作需人工确认 |
| Prompt | 提示词，定义 Agent 的行为和职责 |

---

> **文档结束**
