# ResumeParser Agent + MCP Tool System

> 基于 Momus 审核修正版（2026-05-31）
> 核心原则：工具定义一次（app/tools/），Agent 编排工作流，避免重复

---

## Momus 审核修正

| 问题 | 发现 | 修正 |
|------|------|------|
| 工具定义重复源 | Agent 和 tool 两处定义同一工具 | Agent 不定义工具，只编排工作流 |
| _BUILTIN_TOOLS 重复 | app/tools/ + agent_service.py 都维护工具 | 迁移 _BUILTIN_TOOLS 到 app/tools/ |
| Prompt-H 太长 | 461 行，80% 是示例，不适合直接做 system prompt | 抽取核心 ~80 行，示例裁剪 |
| 7-step 工作流用 LLM 驱动 | 每步调 LLM → 慢且贵 | Agent 代码实现，LLM 只在 parse 和评估介入 |
| Resume API 绕路 | Agent 可能绕过现有后端逻辑 | Agent 调用内部 Service 方法 |

---

## 架构

```
app/tools/                          ← 系统内置工具（定义一次）
├── __init__.py                     ← 自动发现 + all_tools() + all_handlers()
├── resume_parser.py                ← parse_resume, batch_parse, get_profile
├── screening.py                    ← match_candidate, screen_candidate, get_queue
└── interview.py                    ← schedule_interview, send_invite, record_feedback

app/agents/prompts/
└── resume_parser.md                ← ~80 行精简系统提示词

app/agents/
└── resume_parser.py                ← 7-step 工作流编排，不定义工具

迁移:
  app/services/agent_service.py     ← _BUILTIN_TOOLS → from app.tools import all_tools
```

### 工具 vs Skill 区别

| | Skill | Tool |
|--|-------|------|
| 用途 | 外部可插拔插件 | 系统内置能力 |
| 例子 | weather, web_search | parse_resume, match_candidate |
| 安装 | 可选，动态安装 | 开箱即用，始终可用 |
| 目录 | `app/skills/` | `app/tools/` |

---

## 执行计划

### P0 — 框架 + ResumeParser（当前会话）

#### 0A: `app/tools/` 基础设施

```
app/tools/__init__.py:
  def discover_tools() -> dict[str, dict]:
    扫描 app/tools/ 子模块
    每个模块导出 tools (list[dict]) + handlers (dict[str, callable])
    返回 {tool_name: {schema, handler}}

  all_tools() -> list[dict]:
    合并所有 tools 的 schema

  all_handlers() -> dict[str, callable]:
    合并所有 handlers

格式（复用 OpenAI function-calling schema）:
  {
      "type": "function",
      "function": {
          "name": "parse_resume",
          "description": "...",
          "parameters": {"type": "object", "properties": {...}}
      },
      "handler": _handle_parse_resume  ← 附加字段，不入 agent_service
  }
```

**文件**: `app/tools/__init__.py`（新建）

---

#### 0B: `app/tools/resume_parser.py` — 简历解析工具集

3 个工具，handler 调用现有 `CandidateService` + `resume_extractor`：

```
parse_resume(content, file_url, file_type, target_job_id) → structured data
  handler: _handle_parse_resume
    1. 调用 resume_extractor.extract_from_text() — LLM 提取
    2. 降级到 resume_parser.parse_resume() — 规则兜底
    3. 调用 CandidateService 去重检查
    4. 调用 PIIFilter 脱敏
    5. 返回结构化结果

batch_parse_resumes(files, source, target_job_id) → batch result
  handler: _handle_batch_parse
    循环调用 parse_resume，聚合结果 + 失败列表

get_candidate_profile(candidate_id) → aggregated profile
  handler: _handle_get_profile
    调用 CandidateService.get_by_id()
    聚合工作经历、面试记录、评估报告
```

**文件**: `app/tools/__init__.py` + `app/tools/resume_parser.py`（新建）

---

#### 0C: `prompts/resume_parser.md` — 精简系统提示词

从 Prompt-H 461 行抽取核心指令约 80 行：

```
# Resume Parser Agent

## 角色
你是简历解析 Agent，负责将非结构化简历转化为结构化候选人数据。
你不是聊天机器人，不回答通用问题，不执行招聘操作。

## 核心职责
1. 格式统一：PDF/Word/图片/文本 → 统一数据结构
2. 信息提取：联系方式、工作经历、教育背景、技能栈
3. 质量评估：完整度评分，标记缺失字段
4. 风险检测：空窗期、频繁跳槽、履历矛盾
5. 去重匹配：与人才库比对
6. 脱敏输出：手机/邮箱部分隐藏

## 工作流（由 Agent 代码执行，非 LLM 循环）
Step 1: 确认来源和格式
Step 2: 调用 parse_resume 工具
Step 3: 校验 confidence
  - < 0.6 → 标记"需人工复核"
  - 0.6-0.8 → 标注待确认字段
  - > 0.8 → 正常通过
Step 4: 质量评估（从 parse_resume 结果读取）
Step 5: 风险检测（从 parse_resume 结果读取）
Step 6: 去重检查（从 parse_resume 结果读取）
Step 7: 输出标准化结果

## 输出格式
- 基本信息 → 联系方式(脱敏) → 工作经历 → 教育背景
- 技能栈 → 匹配标签 → 质量评分 → 风险提示
- 去重状态 → 解析置信度

## 边界
❌ 不回答招聘策略问题 → "这是筛选 Agent 的职责"
❌ 不安排面试 → "这是面试协调 Agent 的职责"
❌ 不评估薪资 → "这是薪酬谈判 Agent 的职责"
❌ 不修改候选人状态
❌ 不生成 JD
```

**文件**: `app/agents/prompts/resume_parser.md`（新建）

---

#### 0D: `ResumeParsingAgent` — 7-step 工作流 Agent

继承 BaseAgent → 类名 `ResumeParsingAgent` → 自动加载 `prompts/resume_parser.md`

```
run(input_data) → dict
  1. 校验输入（source, content/file_url）
  2. 调用 parse_resume（调用 app/tools/resume_parser.py 的 handler）
  3. 结果校验 & 置信度分级
  4. 质量评估摘要
  5. 风险标注
  6. 去重检查
  7. 返回标准化输出

Batch 模式:
  run(action="batch", files=[...], target_job_id)
  → 循环单份 + 聚合统计

Profile 查询:
  run(action="get_profile", candidate_id)
  → 返回聚合画像
```

**文件**: `app/agents/resume_parser.py`（新建）

---

### P1 — 迁移 + 扩展

#### 1A: 迁移 `_BUILTIN_TOOLS` 到 `app/tools/`

```
app/tools/
├── screening.py    ← 从 _BUILTIN_TOOLS 迁入: search_candidates, get_candidate, screen_resume, match_candidate
├── interview.py    ← 从 _BUILTIN_TOOLS 迁入: schedule_interview, record_feedback

agent_service.py:
  _BUILTIN_TOOLS 移除，改为 from app.tools import all_tools, all_handlers
```

**文件**: `app/tools/screening.py`（新建）, `app/tools/interview.py`（新建）, `app/services/agent_service.py`（修改）

---

#### 1B: 注册到 RouterAgent

```
app/agents/router_agent.py:
  _INTENT_MAP 新增 "resume_parser" → ResumeParsingAgent
  意图关键词: ["解析简历", "解析", "parse", "提取", "简历解析"]
```

**文件**: `app/agents/router_agent.py`（修改）

---

### P2 — Tests

#### 2A: 工具单元测试

```
tests/test_tools/
├── test_resume_parser.py    ← 3 个工具的 handler 测试
├── test_screening.py        ← screening 工具 handler 测试
└── test_interview.py        ← interview 工具 handler 测试
```

#### 2B: Agent 工作流测试

```
tests/test_resume_parser_agent.py:
  - 正常解析流程
  - 低置信度降级
  - 去重处理
  - 批量解析
  - 错误输入处理
```

---

## 文件变更清单

| 文件 | 操作 | 隶属 |
|------|------|------|
| `app/tools/__init__.py` | 新建 | P0-0A |
| `app/tools/resume_parser.py` | 新建 | P0-0B |
| `app/agents/prompts/resume_parser.md` | 新建 | P0-0C |
| `app/agents/resume_parser.py` | 新建 | P0-0D |
| `app/tools/screening.py` | 新建 | P1-1A |
| `app/tools/interview.py` | 新建 | P1-1A |
| `app/services/agent_service.py` | 修改（迁移 _BUILTIN_TOOLS） | P1-1A |
| `app/agents/router_agent.py` | 修改（注册 resume_parser） | P1-1B |
| `tests/test_tools/test_resume_parser.py` | 新建 | P2-2A |
| `tests/test_resume_parser_agent.py` | 新建 | P2-2B |

---

## 退出标准

- [ ] `app/tools/` 自动发现系统 work（`all_tools()` 返回所有工具）
- [ ] `_BUILTIN_TOOLS` 全部迁移到 `app/tools/`，`agent_service.py` 引用新路径
- [ ] `ResumeParsingAgent` 的 `run()` 执行完整 7-step 工作流
- [ ] `GET /router/classify '解析这份简历'` → 路由到 `resume_parser`
- [ ] 解析结果符合 Prompt-H 的输出格式规范
- [ ] TypeScript 编译通过 + Python 测试通过
