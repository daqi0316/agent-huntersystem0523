# AI 招聘系统 · 技术架构 PRD

> 版本：v2.0  
> 日期：2026-05-23  
> 作者：qixia  
> 目标：搭建可售卖的 AI 招聘 SaaS 系统

---

## 一、背景与目标

### 1.1 项目背景
从传统 HR 向 AI+招聘技术转型，搭建一套完整的 AI 招聘系统，包含：
- 本地大模型推理（omlx + Qwen3.6）
- 向量数据库检索（bge-m3 嵌入）
- MCP 工具协议（邮件/日历/ATS）
- Obsidian 知识库（长期记忆）
- Next.js 前端工作台（11个页面）

### 1.2 核心目标
1. **短期**：有可演示的 AI 功能，用于求职展示
2. **中期**：核心功能（AI初筛）可跑通，验证价值
3. **长期**：完整 SaaS 产品，对外售卖服务

---

## 二、七图架构体系总览

本系统采用 **7 种 AI Agent 架构模式混合设计**，根据任务复杂度选择最优模式。

### 2.1 架构模式谱系

```
┌─────────────────────────────────────────────────────────────┐
│  图1 单 Agent          → 一个LLM + 工具/检索/记忆            │
│  图2 流水线            → 串行步骤 + Gate质检关卡              │
│  图3 Router            → 意图识别 + 分发到专业分支             │
│  图4 Aggregator        → 并行多LLM + 合并结果                │
│  图5 Orchestrator      → 动态拆解任务 + 并行执行 + 合成      │
│  图6 Gen-Eval循环      → 生成→评估→反馈→迭代               │
│  图7 Human-in-the-Loop → AI自主执行 + 人类随时介入叫停       │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、七张架构图详解

---

### 图1：单 Agent 架构（Single Agent）

```
        ┌─────────┐
  In ──→│   LLM   │──→ Out
        └────┬────┘
             │
    ┌────────┼────────┐
    ↓        ↓        ↓
┌────────┐ ┌──────┐ ┌────────┐
│Retrieval│ │Tools │ │ Memory │
└────────┘ └──────┘ └────────┘
```

#### 3.1.1 架构说明
**单 Agent 架构**是最基础的 AI Agent 模式。一个 LLM 作为"大脑"，外围配备三种能力模块：

| 模块 | 交互方式 | 作用 |
|:---|:---|:---|
| **Retrieval** | Query/Results | 向量检索，从知识库/简历库中搜索匹配信息 |
| **Tools** | Call/Response | 工具调用，执行外部操作（发邮件、查日历等） |
| **Memory** | Read/Write | 记忆读写，保存对话历史、用户偏好、候选人档案 |

#### 3.1.2 三条虚线箭头的含义
- **Query/Results**：LLM 把用户问题翻译成检索条件，向量数据库返回结果，LLM 基于真实数据生成回答
- **Call/Response**：LLM 判断需要调用某个工具，执行后获取结果继续处理
- **Read/Write**：LLM 读取历史记忆辅助决策，把新信息写入记忆供后续使用

#### 3.1.3 招聘场景
**场景：生成 JD**
```
用户输入："帮我写一个高级Java工程师的JD"
    ↓
LLM 自主决策：
  ├── 调用 Memory → 读取公司技术栈偏好、历史优秀JD模板
  ├── 直接生成 → 基于上下文输出完整JD
  └── 无需调用 Retrieval/Tools（纯生成任务）
```

#### 3.1.4 适用页面
- **页面8：JD生成器**（简化版，不走循环）
- **页面11：知识库**（问答式查询SOP和面试题库）
- **页面1：数据看板**（简单查询招聘数据）

#### 3.1.5 技术实现
```python
class SingleAgent:
    def __init__(self, llm, retrieval, tools, memory):
        self.llm = llm
        self.retrieval = retrieval
        self.tools = tools
        self.memory = memory

    def run(self, user_input):
        # LLM 自主决定调用什么
        response = self.llm.generate(user_input, 
            tools=self.tools.available(),
            memory=self.memory.read())
        return response
```

---

### 图2：流水线架构（Pipeline / Chain-of-Agents）

```
  In ──→ LLM Call 1 ──→ Output 1 ──→ Gate ──→ Pass ──→ LLM Call 2 ──→ Output 2 ──→ LLM Call 3 ──→ Out
                                          └──→ Fail ──→ Exit
```

#### 3.2.1 架构说明
**流水线架构**将复杂任务拆分为多个串行的 LLM 调用阶段，每两个阶段之间设置 **Gate（质检关卡）**。Gate 检查中间产物质量，不合格则终止流程，避免"垃圾进垃圾出"。

#### 3.2.2 核心组件
| 组件 | 作用 |
|:---|:---|
| **LLM Call 1/2/3** | 各阶段的专业处理，每阶段只负责一件事 |
| **Output 1/2** | 中间产物，作为下一阶段的输入 |
| **Gate** | 质检关卡，判断中间产物是否合格 |
| **Pass** | 质检通过，进入下一阶段 |
| **Fail** | 质检失败，流程终止并返回错误 |
| **Exit** | 异常退出，不输出最终结果 |

#### 3.2.3 招聘场景
**场景：AI 初筛简历**
```
用户输入JD："高级Java工程师，5年经验，熟悉微服务..."
    ↓
【Call 1】解析JD
  → 提取：技能关键词[Java,Spring Boot,微服务]、经验5年、本科+
  → Output 1：结构化筛选条件
    ↓
【Gate 1】质检
  → 检查：是否缺少薪资范围？是否缺少地点要求？
  → Fail → Exit（"请补充薪资范围"）
  → Pass → 继续
    ↓
【Call 2】向量检索
  → bge-m3嵌入JD → 向量库搜索 → 返回15份匹配简历
  → Output 2：候选人列表
    ↓
【Gate 2】质检
  → 检查：匹配人数>5？平均匹配度>60%？
  → Fail → Exit（"匹配候选人不足，建议放宽条件"）
  → Pass → 继续
    ↓
【Call 3】生成评估报告
  → 分析15份简历，排序，生成推荐理由
  → Out：Top 10候选人名单 + 评估卡片
```

#### 3.2.4 Gate 质检规则示例
```python
def gate_check(output, stage):
    if stage == "parse_jd":
        if not output.get("salary_range"):
            return "Fail", "缺少薪资范围，请补充"
        if not output.get("required_skills"):
            return "Fail", "未提取到硬性技能要求"
    elif stage == "retrieve":
        if len(output["candidates"]) < 5:
            return "Fail", "匹配候选人不足5人，建议放宽条件"
        if output["avg_score"] < 0.6:
            return "Fail", "平均匹配度低于60%，建议优化JD"
    return "Pass", None
```

#### 3.2.5 适用页面
- **页面4：AI初筛**（核心功能，必须走流水线保证质量）
- **页面6：评估报告**（流水线的最后一步）

---

### 图3：路由分发架构（Routing / LLM as Router）

```
  In ──→ LLM Call Router ──→ LLM Call 1 ──→ Out
                         ├──→ LLM Call 2 ──→ Out
                         └──→ LLM Call 3 ──→ Out
```

#### 3.3.1 架构说明
**路由分发架构**先让 AI 判断"这是什么类型的任务"，然后分发到不同的专业处理模块。各模块独立完成后直接输出，互不干扰。

#### 3.3.2 核心组件
| 组件 | 作用 |
|:---|:---|
| **LLM Call Router** | 智能分诊员，分析输入判断任务类型 |
| **LLM Call 1/2/3** | 专科医生，各自只处理一类任务 |
| **Out** | 各分支独立输出 |

#### 3.3.3 与图2（流水线）的区别
| | 流水线（图2） | 路由分发（图3） |
|:---|:---|:---|
| **流程关系** | 串行，前一阶段输出是后一阶段输入 | 并行/独立，各分支互不依赖 |
| **适用任务** | 复杂单任务，需要多步骤拆解 | 多种独立任务，每类有专属逻辑 |
| **分支数量** | 2分支（Pass/Fail） | 3+分支（按任务类型） |
| **失败影响** | Gate Fail 整个流程终止 | 某分支失败不影响其他分支 |

#### 3.3.4 招聘场景
**场景：多功能招聘平台**
```
用户输入不同指令，Router自动分发：

"帮我写个Java工程师的JD"     → Router判断：文案生成类 → LLM Call 1（JD生成）
"筛选库里3年经验的候选人"      → Router判断：检索匹配类 → LLM Call 2（简历检索）
"分析张三的面试表现"          → Router判断：评估分析类 → LLM Call 3（评估报告）
"发面试通知给张三"            → Router判断：工具调用类 → LLM Call 4（邮件发送）
```

#### 3.3.5 Router 意图分类实现
```python
prompt = """
分析用户输入，判断任务类型，只输出JSON：
{
  "intent": "write_jd|screen_resume|evaluate_candidate|send_email|query_data|chat",
  "confidence": 0-1,
  "missing_info": []
}

用户输入：{user_input}
"""
```

#### 3.3.6 适用页面
- **页面2：职位管理**（创建JD走图6循环，发布职位走图7人机协作）
- **页面10：系统设置**（不同设置项分发到不同处理模块）

---

### 图4：聚合器架构（Aggregator / Parallel Processing）

```
  In ──→ LLM Call 1 ──┐
       LLM Call 2 ───→ Aggregator ──→ Out
       LLM Call 3 ───┘
```

#### 3.4.1 架构说明
**聚合器架构**将一个任务同时丢给多个 LLM **并行处理**，每个 LLM 从**不同角度**分析，最后由 **Aggregator（聚合器）** 把多个结果合并成统一输出。

#### 3.4.2 核心组件
| 组件 | 作用 |
|:---|:---|
| **LLM Call 1/2/3** | 并行执行，各从一个角度分析同一任务 |
| **Aggregator** | 结果合并器，加权整合多个角度分析 |
| **Out** | 统一输出，综合多维度结论 |

#### 3.4.3 与图3（Router）的区别
| | Router（图3） | Aggregator（图4） |
|:---|:---|:---|
| **任务分配** | 一个任务分给**一个**专业模块 | 一个任务分给**多个**模块同时处理 |
| **输出** | 各分支独立输出，互不干扰 | 必须合并成一个统一结果 |
| **适用** | 任务类型明确不同（写JD vs 发邮件） | 同一任务需要多角度分析（评估候选人） |
| **成本** | 低（只走一个分支） | 高（同时调用3次LLM） |

#### 3.4.4 招聘场景
**场景：多维度候选人评估**
```
用户："评估候选人张三是否适合高级Java工程师岗位"
    ↓
并行调用3个LLM：

LLM Call 1（技术评估）：
  → 分析技术栈匹配度：Java 95%、Spring Boot 90%、微服务 85%
  → 技术评分：90分

LLM Call 2（文化契合评估）：
  → 分析价值观、团队风格、沟通方式匹配度
  → 文化评分：75分

LLM Call 3（潜力评估）：
  → 分析学习能力、成长轨迹、职业规划
  → 潜力评分：88分
    ↓
Aggregator合并：
  → 加权计算：90×0.4 + 75×0.3 + 88×0.3 = 85.9分
  → 综合推荐："技术扎实，文化契合度中等，潜力良好。建议通过初筛，重点考察团队协作能力。"
```

#### 3.4.5 Aggregator 合并逻辑
```python
def aggregate(tech_score, culture_score, potential_score):
    weighted = tech_score * 0.4 + culture_score * 0.3 + potential_score * 0.3
    if weighted >= 85:
        return "强烈推荐"
    elif weighted >= 70:
        return "推荐面试"
    elif weighted >= 60:
        return "待定，需进一步考察"
    else:
        return "暂不推荐"
```

#### 3.4.6 适用页面
- **页面4：AI初筛**（Step 3 评估阶段，多维度评分合并）
- **页面7：人才画像**（多维度人才分析）
- **页面9：数据报表**（多数据源并行查询合并）

---

### 图5：编排器架构（Orchestrator + Synthesizer）

```
  In ──→ Orchestrator ──→ LLM Call 1 ──┐
                     ├→ LLM Call 2 ───→ Synthesizer ──→ Out
                     └→ LLM Call 3 ───┘
```

#### 3.5.1 架构说明
**编排器架构**由 **Orchestrator（编排器）** 先分析任务，**动态决定**需要哪些子任务、每个任务是什么，然后并行执行，最后由 **Synthesizer（合成器）** 把结果整合成最终输出。

#### 3.5.2 核心组件
| 组件 | 作用 |
|:---|:---|
| **Orchestrator** | 任务编排器，动态拆解任务为子任务列表 |
| **LLM Call 1/2/3** | 并行执行编排器分配的子任务 |
| **Synthesizer** | 结果合成器，智能整合子任务结果为完整报告 |

#### 3.5.3 与图4（Aggregator）的区别
| | Aggregator（图4） | Orchestrator（图5） |
|:---|:---|:---|
| **任务拆分** | 人类预设3个固定角度 | **AI 动态决定**需要几个子任务、每个任务是什么 |
| **灵活性** | 低，角度固定 | 高，根据输入自适应拆解 |
| **智能度** | 机械合并 | 智能编排+智能合成 |

#### 3.5.4 招聘场景
**场景：全面招聘分析报告**
```
用户："帮我做一个Q2招聘分析报告"
    ↓
Orchestrator动态拆解：
  1. 分析Q2招聘漏斗数据（投递→初筛→面试→offer→入职）
  2. 分析各渠道转化率（BOSS直聘、猎聘、内推、官网）
  3. 分析候选人质量分布（学历、经验、来源）
  4. 分析OTD周期变化趋势
  5. （检测到用户提到竞品）分析竞品招聘动态
    ↓
并行执行5个子任务
    ↓
Synthesizer合成：
  → "Q2招聘效率下降15%，主要原因是渠道A转化率降低。
     建议：加大渠道B投入，优化JD关键词。
     竞品正在抢Java人才，建议加快面试节奏。
     预计Q3需增加2名招聘专员。"
```

#### 3.5.5 适用页面
- **页面7：人才画像**（动态拆解多维度分析）
- **页面9：数据报表**（复杂综合分析报告）

---

### 图6：生成-评估循环架构（Generator + Evaluator Loop）

```
  In ──→ LLM Call Generator ──→ Solution ──→ LLM Call Evaluator
              ↑                                    │
              └────── Rejected + Feedback ─────────┘
                                                  Accepted ──→ Out
```

#### 3.6.1 架构说明
**生成-评估循环架构**由 **Generator（生成器）** 生成结果，**Evaluator（评估器）** 评估质量。不合格则反馈给 Generator 重新生成，循环迭代直到合格。

#### 3.6.2 核心组件
| 组件 | 作用 |
|:---|:---|
| **Generator** | 生成器，产出初始方案/内容 |
| **Evaluator** | 评估器，按 checklist 检查质量 |
| **Solution** | 生成的方案/内容 |
| **Rejected + Feedback** | 不合格反馈，包含具体改进建议 |
| **Accepted** | 评估通过，输出最终结果 |

#### 3.6.3 招聘场景
**场景：高质量面试问题生成**
```
用户："为高级Java工程师岗位生成5个面试题"
    ↓
【第1轮】
Generator生成5个题目
Evaluator检查：
  □ 是否考察分布式经验？  ❌ 缺少
  □ 是否包含行为面试题？  ❌ 缺少
  → Rejected + Feedback："补充分布式架构题和BEI行为题"
    ↓
【第2轮】
Generator重新生成（加入分布式+BEI）
Evaluator检查：
  □ 是否考察分布式经验？  ✓
  □ 是否包含行为面试题？  ✓
  □ 难度是否适中？        ❌ 偏难
  → Rejected + Feedback："降低技术题难度至中级"
    ↓
【第3轮】
Generator再次生成
Evaluator检查：全部通过
  → Accepted → Out（高质量面试题）
```

#### 3.6.4 最大迭代次数控制
```python
MAX_ITERATIONS = 3  # 防止无限循环

def generate_with_eval(user_input):
    for i in range(MAX_ITERATIONS):
        solution = generator.generate(user_input, feedback=feedback)
        result, feedback = evaluator.evaluate(solution)
        if result == "Accepted":
            return solution
    return solution  # 超过最大次数，返回最后一版
```

#### 3.6.5 适用页面
- **页面8：JD生成器**（核心功能，必须高质量）
- **页面6：评估报告**（需要结构化、无遗漏）

---

### 图7：人机协作循环架构（Human-in-the-Loop）

```
  Human ←────→ LLM Call ←────→ Environment
                  ↓
                Stop
```

#### 3.7.1 架构说明
**人机协作循环架构**中，AI 在环境中**自主执行动作**、获取反馈、继续执行；人类与 AI 保持双向交互，**随时可介入叫停或指导**。

#### 3.7.2 核心组件
| 组件 | 作用 |
|:---|:---|
| **Human** | 人类用户，可观察状态、下达指令、接管控制 |
| **LLM Call** | AI 大脑，决策下一步动作 |
| **Environment** | 外部环境，执行动作后返回结果 |
| **Action** | AI 执行的动作（发邮件、查日历、更新系统） |
| **Feedback** | 环境返回的结果（邮件已发送、候选人回复、系统报错） |
| **Stop** | 紧急制动，人类可随时终止 AI 执行 |

#### 3.7.3 招聘场景
**场景：AI 自动寻访候选人**
```
AI: 搜索LinkedIn找到10个匹配候选人
    ↓
AI: 发送个性化邀约邮件给候选人A
    ↓
Environment反馈: 候选人A已读未回
    ↓
AI: 3天后发送跟进邮件
    ↓
Human看到界面：
  ┌─────────────────────────────────────┐
  │ 候选人A：已发送邮件，已读未回          │
  │ 候选人B：已发送邮件，已回复感兴趣       │
  │ [查看详情] [Stop接管] [调整策略]       │
  └─────────────────────────────────────┘
    ↓
Human点击"Stop" → AI暂停 → Human接管联系候选人B
```

#### 3.7.4 为什么必须有 Stop
- **防止错误扩散**：AI 发错邮件给候选人，人类可立即叫停
- **关键决策人类把关**：offer 发放、薪资谈判等敏感操作需人类确认
- **信任建立**：让用户感到"AI 在帮我，但我随时可控"

#### 3.7.5 适用页面
- **页面5：面试安排**（AI协调日历+发邮件，人类确认后执行）
- **页面2：职位管理**（发布职位到外部平台，人类确认）
- **自动寻访功能**（AI主动联系候选人，人类随时接管）

---

## 四、七图对比总表

| 图 | 模式 | 结构 | 核心节点 | 适用场景 | 成本 | 质量 | 可控性 |
|:---|:---|:---|:---|:---|:---|:---|:---|
| **图1** | 单 Agent | 星型 | LLM + 工具/检索/记忆 | 开放式问答、创意生成 | 低 | 中 | 低 |
| **图2** | 流水线 | 链型 | Gate 质检关卡 | 标准化流程（简历筛选） | 中 | 高 | 高 |
| **图3** | Router | 树型 | Router 分发器 | 多种独立任务 | 中 | 高 | 中 |
| **图4** | Aggregator | 并行型 | Aggregator 合并器 | 多角度分析 | 高 | 很高 | 中 |
| **图5** | Orchestrator | 动态并行 | Orchestrator+Synthesizer | 复杂综合分析 | 很高 | 最高 | 中 |
| **图6** | Gen-Eval | 循环型 | Evaluator 评估器 | 高质量生成 | 高 | 最高 | 高 |
| **图7** | Human-in-Loop | 交互型 | Human + Environment | 涉及外部系统 | 中 | 高 | **最高** |

---

## 五、系统整体架构

### 5.1 三层架构图

```
┌─────────────────────────────────────────┐
│           前端层 (Next.js 11页面)        │
│  数据看板 │ 职位管理 │ 候选人库 │ AI初筛 │
│  面试安排 │ 评估报告 │ 人才画像 │ JD生成 │
│  数据报表 │ 系统设置 │ 知识库              │
├─────────────────────────────────────────┤
│           编排层 (7种Agent模式)          │
│  Router → 单Agent/流水线/Aggregator/    │
│  Orchestrator/Gen-Eval/Human-in-Loop    │
├─────────────────────────────────────────┤
│           基础设施层                      │
│  omlx+Qwen3.6 │ 向量库+bge-m3 │ MCP工具 │
│  Obsidian知识库 │ Next.js前端              │
└─────────────────────────────────────────┘
```

### 5.2 全局 Router 设计

```python
class GlobalRouter:
    """
    全局意图识别 + 架构模式选择
    """
    def route(self, user_input, context):
        """
        返回: {
            "intent": "screen_resume|write_jd|schedule_interview|...",
            "architecture": "pipeline|single_agent|aggregator|...",
            "confidence": 0.95,
            "required_pages": [4, 6]
        }
        """
        # 意图分类
        intent = self.classify_intent(user_input)

        # 架构模式选择
        architecture_map = {
            "write_jd": "gen_eval",           # JD生成用循环保证质量
            "screen_resume": "pipeline",       # 简历筛选用流水线标准化
            "evaluate_candidate": "aggregator", # 候选人评估多角度并行
            "schedule_interview": "human_loop", # 面试安排必须人类确认
            "query_data": "single_agent",      # 数据查询简单快速
            "complex_analysis": "orchestrator" # 复杂分析动态拆解
        }

        return {
            "intent": intent,
            "architecture": architecture_map.get(intent, "single_agent"),
            "confidence": 0.95
        }
```

---

## 六、11页面与七图映射

### 6.1 映射总表

| 页面 | 名称 | 主架构 | 辅助架构 | 核心功能 | 优先级 |
|:---|:---|:---|:---|:---|:---|
| 1 | **数据看板** | 图1 单Agent | - | 招聘漏斗、转化率、OTD | P2 |
| 2 | **职位管理** | 图3 Router | 图6/图7 | 创建/编辑/发布职位 | P1 |
| 3 | **候选人库** | 图1 单Agent+RAG | - | 简历存储、标签、搜索 | P1 |
| 4 | **AI初筛** | **图2 流水线** | **图4 Aggregator** | JD解析→检索→匹配→评估 | **P0** |
| 5 | **面试安排** | **图7 Human-in-Loop** | - | 日历协调、邮件通知、人类确认 | P1 |
| 6 | **评估报告** | 图2 流水线 | 图6 Gen-Eval | 结构化面试评估报告 | P1 |
| 7 | **人才画像** | **图5 Orchestrator** | 图4 Aggregator | 多维度人才分析 | P2 |
| 8 | **JD生成器** | **图6 Gen-Eval** | - | 高质量JD生成 | P1 |
| 9 | **数据报表** | 图4 Aggregator | 图5 Orchestrator | 多数据源合并报表 | P2 |
| 10 | **系统设置** | 无AI | - | 模型配置、API密钥 | P1 |
| 11 | **知识库** | 图1 单Agent+RAG | - | SOP文档、面试题库问答 | P1 |

### 6.2 核心页面详细设计

#### 页面4：AI初筛（流水线 + Aggregator）

```
用户输入JD文本
    ↓
【Step 1】Call 1: 解析JD
  - LLM提取：技能关键词、经验要求、学历、薪资、地点
  - Gate检查：是否缺少关键信息？
    ├── Fail → Exit（提示补充薪资范围/经验要求）
    └── Pass → 继续
    ↓
【Step 2】Call 2: 向量检索
  - bge-m3嵌入JD → 向量库搜索 → 返回匹配简历
  - Gate检查：匹配人数>5？匹配度>60%？
    ├── Fail → Exit（建议放宽条件）
    └── Pass → 继续
    ↓
【Step 3】Aggregator: 多维度评估
  - 并行调用3个LLM：
    * Call A: 技术能力评分（技术栈匹配度）
    * Call B: 文化契合评分（价值观/团队匹配）
    * Call C: 潜力评分（成长空间/学习能力）
  - Aggregator合并：加权计算综合得分
    ↓
输出：Top 10候选人 + 三维评分雷达图 + 推荐理由
```

**Aggregator 合并逻辑**：
```python
def aggregate(tech_score, culture_score, potential_score):
    weighted = tech_score * 0.4 + culture_score * 0.3 + potential_score * 0.3
    if weighted >= 85:
        return "强烈推荐"
    elif weighted >= 70:
        return "推荐面试"
    elif weighted >= 60:
        return "待定，需进一步考察"
    else:
        return "暂不推荐"
```

---

#### 页面8：JD生成器（Gen-Eval循环）

```
用户输入：岗位名称+基本要求
    ↓
Generator v1: 生成初稿JD
    ↓
Evaluator检查清单：
  □ 是否包含5条以上职责描述？
  □ 是否包含明确任职要求（学历/经验/技能）？
  □ 是否包含薪资范围或薪资竞争力说明？
  □ 是否包含公司/团队亮点吸引候选人？
  □ 语言是否专业且无歧视性词汇？
    ↓
Rejected → 反馈具体问题 → Generator v2
    ↓
（最多迭代3轮）
    ↓
Accepted → 输出高质量JD
```

---

#### 页面5：面试安排（Human-in-the-Loop）

```
用户：安排张三面试
    ↓
AI Orchestrator:
  1. 查日历API → 面试官李经理空闲时段：周一14:00、周三15:00、周五10:00
  2. 查候选人偏好 → 张三备注：偏好下午
  3. 生成邮件草稿
    ↓
【人类确认界面】
  ┌─────────────────────────────────────┐
  │ 推荐时段：周三 15:00（匹配候选人偏好） │
  │ 面试官：李经理                       │
  │ 地点：会议室A / 线上腾讯会议           │
  │                                      │
  │ [邮件预览]                           │
  │ 张三先生，您好！邀请您参加...          │
  │                                      │
  │ [✓ 确认发送]  [✎ 修改]  [✕ 取消]    │
  │ [⏹ Stop - 我来手动处理]              │
  └─────────────────────────────────────┘
    ↓
人类点击确认 → AI执行：发邮件 + 预约日历 + 更新候选人状态
人类点击Stop → AI暂停，人类接管
```

---

## 五、技术架构设计（企业级方案）

> 面向生产环境，强调可扩展性、稳定性和可维护性。

---

### 5.1 整体架构

```
部署层: Vercel Edge / Cloudflare Pages / CDN
    ↓ HTTPS / gRPC
网关层: Traefik / Kong (SSL终止、限流、认证、A/B Test)
    ↓
前端层 (Next.js 14)              后端层 (FastAPI)
App Router │ RSC │ Streaming      Uvicorn │ Gunicorn │ 多实例
tRPC │ React Query │ Zustand      七图编排引擎 │ 异步任务队列
    ↓                                    ↓
AI推理集群 (vLLM+Qwen GPU)      数据存储层          基础设施
                                PostgreSQL 主从      Redis 集群
                                Qdrant 向量库       RabbitMQ
                                MinIO 对象存储      Prometheus
                                TimescaleDB         Grafana
                                ClickHouse          Loki
```

---

## 六、后端技术架构

### 6.1 API 服务层：FastAPI + Uvicorn + Gunicorn

**选型理由**：Python 是 AI/ML 唯一生态；FastAPI 异步原生，性能碾压同步框架；自动 OpenAPI 文档；Pydantic v2 类型安全。

**Gunicorn 作用**：管理多 Uvicorn worker 进程，充分利用多核 CPU，进程隔离崩溃不影响其他请求。

```python
# gunicorn.conf.py
import multiprocessing
bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
keepalive = 5
timeout = 120
graceful_timeout = 30
max_requests = 10000
```

```python
# main.py 核心结构
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await app.state.db.connect()
    await app.state.redis.connect()
    await app.state.qdrant.connect()
    yield
    await app.state.db.disconnect()
    await app.state.redis.disconnect()
    await app.state.qdrant.disconnect()

app = FastAPI(title="AI Recruitment API", version="1.0.0", lifespan=lifespan)
# 注册七图路由
app.include_router(agent.router, prefix="/api/v1/agent")      # 图1
app.include_router(pipeline.router, prefix="/api/v1/pipeline")  # 图2
app.include_router(router.router, prefix="/api/v1/router")  # 图3
app.include_router(parallel.router, prefix="/api/v1/parallel")  # 图4
app.include_router(orchestrator.router, prefix="/api/v1/orchestrator")  # 图5
app.include_router(loop.router, prefix="/api/v1/loop")      # 图6
app.include_router(human_loop.router, prefix="/api/v1/human-loop")  # 图7
```

### 6.2 AI 推理层：vLLM + GPU

| 方案 | 吞吐量 | 延迟 | 并发 | 适用场景 |
|:---|:---|:---|:---|:---|
| **vLLM** | 极高 | 低 | 高 | 生产级 GPU 推理 |
| omlx | 中 | 中 | 低 | 开发测试 |
| llama.cpp | 中 | 低 | 中 | CPU 推理 |
| TensorRT-LLM | 极高 | 极低 | 极高 | NVIDIA 专用 |

**vLLM 核心优势**：PagedAttention 内存高效；Continuous Batching 吞吐量提升 10x；OpenAI 兼容 API；多 GPU Tensor Parallelism。

```yaml
# vLLM Docker 配置
services:
  vllm:
    image: vllm/vllm-openai:latest
    runtime: nvidia
    environment:
      - CUDA_VISIBLE_DEVICES=0,1
    command: >
      --model /models/Qwen3.6-32B
      --tensor-parallel-size 2
      --max-num-seqs 256
      --gpu-memory-utilization 0.9
      --dtype bfloat16
      --enable-prefix-caching
```

### 6.3 向量数据库：Qdrant

| 数据库 | 部署方式 | 性能 | 适用场景 |
|:---|:---|:---|:---|
| **Qdrant** | 本地/Docker/K8s | 极高，Rust 编写 | 最佳选择 |
| Pinecone | 纯 SaaS | 高 | 数据出域，有费用 |
| Milvus | Docker/K8s | 高 | 运维复杂 |
| Weaviate | Docker/K8s | 中高 | 功能过剩 |
| ChromaDB | 本地文件 | 中 | 非生产级 |

```python
# Qdrant 服务封装
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, Range

class QdrantService:
    def __init__(self, host="localhost", port=6333):
        self.client = QdrantClient(host=host, port=port, grpc_port=6334)
        self.embedder = SentenceTransformer('BAAI/bge-m3', device='cuda')
        self.collection_name = "resumes"
        self.vector_size = 1024

    def search(self, query, filters=None, limit=10):
        query_embedding = self.embedder.encode(query, normalize_embeddings=True)
        must_conditions = []
        if filters:
            if "min_experience" in filters:
                must_conditions.append(FieldCondition(
                    key="experience_years", range=Range(gte=filters["min_experience"])
                ))
            if "location" in filters:
                must_conditions.append(FieldCondition(
                    key="location", match={"value": filters["location"]}
                ))

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding.tolist(),
            query_filter=Filter(must=must_conditions) if must_conditions else None,
            limit=limit,
            score_threshold=0.7
        )
        return results
```

### 6.4 数据库：PostgreSQL 16 主从 + 读写分离

| 特性 | PostgreSQL 16 | MySQL 8 | MongoDB | SQLite |
|:---|:---|:---|:---|:---|
| ACID | 完整 | 完整 | 最终一致 | 完整 |
| JSONB | 原生 | 需插件 | 原生 | 无 |
| 全文搜索 | 内置 | 需 ES | 有限 | 无 |
| 扩展生态 | 丰富 | 中等 | 少 | 无 |
| 复杂查询 | 极强 | 中等 | 弱 | 有限 |
| 并发扩展 | 主从+分片 | 主从 | 分片 | 单文件 |

```python
# SQLAlchemy 异步引擎 + 读写分离
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

class PostgresManager:
    def __init__(self, primary_url, replica_url=None):
        self.primary_engine = create_async_engine(
            primary_url, pool_size=20, max_overflow=30, pool_pre_ping=True
        )
        self.replica_engine = create_async_engine(
            replica_url or primary_url, pool_size=30, max_overflow=50
        ) if replica_url else self.primary_engine

        self.async_session = async_sessionmaker(
            self.primary_engine, class_=AsyncSession, expire_on_commit=False
        )

    @asynccontextmanager
    async def session(self):  # 写操作
        async with self.async_session() as session:
            try: yield session; await session.commit()
            except: await session.rollback(); raise
            finally: await session.close()

    @asynccontextmanager
    async def read_session(self):  # 读操作
        async with AsyncSession(self.replica_engine) as session:
            yield session
```

**核心模型**：Candidate（候选人）、JobPosition（职位）、JobApplication（申请）、Interview（面试）——全部使用 UUID 主键、JSONB 存储 AI 评分、ARRAY 存储技能标签、复合索引优化查询。

### 6.5 缓存层：Redis 7

用途：会话存储、限流计数器、热点数据、分布式锁、任务队列配合 Celery。

```python
class RedisService:
    def __init__(self, url="redis://localhost:6379"):
        self.client = redis.from_url(url, max_connections=50)

    async def get_json(self, key): ...
    async def set_json(self, key, value, expire=3600): ...
    async def acquire_lock(self, lock_name, timeout=10): ...
    async def is_rate_limited(self, key, max_requests, window): ...
```

### 6.6 消息队列：RabbitMQ

用途：异步任务（AI 初筛、邮件发送、报表生成）、削峰填谷、解耦、可靠投递。

### 6.7 对象存储：MinIO

S3 兼容 API，分布式纠删码，用于简历 PDF/Word 文件、头像、导出报表。

### 6.8 可观测性：Prometheus + Grafana + Loki

```python
# Prometheus 指标
REQUEST_COUNT = Counter('http_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'Request duration', ['endpoint'])
AI_INFERENCE_DURATION = Histogram('ai_inference_duration_seconds', 'AI inference time', ['model'])
```

### 6.9 后端依赖清单

```txt
fastapi==0.111.0
uvicorn[standard]==0.30.0
pydantic==2.7.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.0
qdrant-client==1.9.0
sentence-transformers==3.0.0
langchain==0.2.0
httpx==0.27.0
aio-pika==9.4.0
redis==5.0.0
minio==7.2.0
mcp==1.0.0
prometheus-client==0.20.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
```

---

## 七、前端技术架构

### 7.1 Monorepo：Turborepo + pnpm

```
ai-recruitment/
├── apps/
│   ├── web/          # 主应用 (Next.js 14)
│   ├── admin/        # 管理后台
│   └── docs/         # 文档站
├── packages/
│   ├── ui/           # 共享组件库
│   ├── types/        # 共享 TypeScript 类型
│   ├── config/       # 共享配置
│   └── utils/        # 共享工具函数
```

### 7.2 类型系统：端到端类型安全

数据库 Schema → Zod 验证 → tRPC 路由 → React Query Hook → 前端组件，全程类型推导，零运行时错误。

### 7.3 API 层：tRPC + React Query

**为什么不是 REST/GraphQL？**

| 方案 | 类型安全 | 样板代码 | 学习成本 | 适用场景 |
|:---|:---|:---|:---|:---|
| **tRPC** | 端到端 | 极少 | 中 | 最佳选择 |
| REST + OpenAPI | 需生成 | 多 | 低 | 重复定义 |
| GraphQL | 有 | 多 | 高 | 过度设计 |

```typescript
// tRPC Router 示例
export const candidateRouter = router({
  list: protectedProcedure
    .input(z.object({ cursor: z.string().optional(), limit: z.number().default(20) }))
    .query(async ({ ctx, input }) => {
      const candidates = await ctx.prisma.candidate.findMany({
        take: input.limit + 1,
        cursor: input.cursor ? { id: input.cursor } : undefined,
        orderBy: { createdAt: 'desc' },
      });
      return { candidates, nextCursor };
    }),

  screenResume: protectedProcedure
    .input(ScreenResumeSchema)
    .mutation(async ({ ctx, input }) => {
      return await ctx.pipelineEngine.execute(input);
    }),
});
```

### 7.4 状态管理：Zustand + React Query 分层

**核心原则**：服务端状态走 React Query，客户端状态走 Zustand，绝不混用。

```typescript
// React Query：服务端状态（缓存、重试、分页）
export function useCandidates(filters?: CandidateFilters) {
  return useQuery({
    queryKey: ['candidates', filters],
    queryFn: ({ pageParam }) => api.candidate.list.query({ cursor: pageParam, filters }),
    staleTime: 1000 * 60 * 5,  // 5分钟不重复请求
  });
}

// Zustand：客户端状态（UI、主题、选中项）
export const useUIStore = create<UIState>()(
  devtools(persist((set) => ({
    sidebarCollapsed: false,
    theme: 'system',
    selectedCandidateId: null,
    filters: {},
    toggleSidebar: () => set(s => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    setTheme: (theme) => set({ theme }),
    setSelectedCandidate: (id) => set({ selectedCandidateId: id }),
  }), { name: 'ui-storage' }))
);
```

### 7.5 组件架构

```
components/
├── ui/              # shadcn/ui 基础组件（不修改）
├── common/          # 业务通用组件（sidebar, header, data-table）
└── features/        # 功能模块组件（按页面组织）
    ├── screening/   # AI初筛相关
    ├── interview/   # 面试安排相关
    └── report/      # 报表相关
```

**设计原则**：`ui/` 纯展示无业务逻辑；`common/` 跨页面复用可配置；`features/` 业务耦合可调用 hooks；禁止跨 feature 引用。

### 7.6 服务端组件策略（RSC）

```tsx
// page.tsx - Server Component，服务端获取数据
export default async function ScreeningPage() {
  const { recentJobs } = await getInitialData();  // 服务端直接查数据库
  return (
    <div>
      <JobSelector initialJobs={recentJobs} />  {/* 服务端渲染 */}
      <Suspense fallback={<Skeleton />}>
        <ScreeningClient />  {/* 客户端交互部分 */}
      </Suspense>
    </div>
  );
}
```

### 7.7 实时通信：Server-Sent Events

AI 初筛流水线进度实时推送，Gate 质检状态可视化。

```typescript
export function usePipelineProgress(pipelineId: string) {
  useEffect(() => {
    const eventSource = new EventSource(`/api/pipeline/${pipelineId}/progress`);
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'step_complete') setSteps(prev => [...prev, data.step]);
      if (data.type === 'gate_check') updateGateStatus(data);
    };
    return () => eventSource.close();
  }, [pipelineId]);
}
```

### 7.8 主题系统：CSS Variables + Tailwind

设计令牌（颜色、间距、圆角）通过 CSS Variables 定义，支持 light/dark/system 三模式切换。

### 7.9 测试策略

| 类型 | 工具 | 覆盖范围 |
|:---|:---|:---|
| 单元测试 | Vitest + @testing-library/react | 组件、hooks、工具函数 |
| E2E测试 | Playwright | 核心用户流程 |
| 视觉测试 | Storybook | 组件文档化、交互测试 |

### 7.10 部署：Vercel Pro

ISR 增量静态再生、Edge Functions、全球 CDN、Cron 定时任务、Analytics 性能监控。

### 7.11 前端依赖清单

```json
{
  "dependencies": {
    "next": "^14.2.0", "react": "^18.3.0", "typescript": "^5.4.0",
    "@trpc/client": "^11.0.0", "@trpc/server": "^11.0.0", "@trpc/react-query": "^11.0.0",
    "@tanstack/react-query": "^5.0.0", "superjson": "^2.0.0", "zod": "^3.23.0",
    "zustand": "^4.5.0", "tailwindcss": "^3.4.0", "@radix-ui/react-dialog": "^1.0.0",
    "recharts": "^2.12.0", "react-hook-form": "^7.51.0", "lucide-react": "^0.378.0"
  },
  "devDependencies": {
    "vitest": "^1.6.0", "@testing-library/react": "^15.0.0",
    "playwright": "^1.44.0", "husky": "^9.0.0", "turbo": "^2.0.0"
  }
}
```

---

## 八、Docker Compose 生产配置

```yaml
version: '3.8'
services:
  api-1/2/3:          # 3实例 FastAPI
  traefik:            # 网关负载均衡
  postgres-primary:   # 主库
  postgres-replica:   # 从库
  qdrant:             # 向量库
  redis-master-1:     # 缓存
  rabbitmq:           # 消息队列
  vllm:               # AI推理（GPU）
  minio:              # 对象存储
  prometheus:         # 监控采集
  grafana:            # 监控可视化
```

---

## 九、技术栈总结

### 后端

| 层级 | 技术 | 部署 | 扩展 |
|:---|:---|:---|:---|
| 网关 | Traefik | Docker | 配置热更新 |
| API | FastAPI + Uvicorn + Gunicorn | Docker × N | 水平扩展 |
| AI推理 | vLLM | Docker + GPU | 增加 GPU 节点 |
| 向量库 | Qdrant | Docker | 集群分片 |
| 数据库 | PostgreSQL 16 主从 | Docker | 读写分离 |
| 缓存 | Redis 7 | Docker | Sentinel + Cluster |
| 消息队列 | RabbitMQ | Docker | 镜像队列 |
| 对象存储 | MinIO | Docker | 纠删码 |
| 监控 | Prometheus + Grafana + Loki | Docker | 联邦集群 |

### 前端

| 层级 | 技术 | 版本 | 作用 |
|:---|:---|:---|:---|
| Monorepo | Turborepo + pnpm | latest | 多包管理 |
| 框架 | Next.js | 14+ | App Router、RSC |
| 语言 | TypeScript | 5.4+ | 类型安全 |
| 样式 | Tailwind + CSS Variables | 3.4+ | 主题系统 |
| 组件库 | shadcn/ui + Radix | latest | 可访问性 |
| 状态 | Zustand + React Query | 4+/5+ | 分层管理 |
| API | tRPC + SuperJSON | 11+ | 端到端类型安全 |
| 验证 | Zod | 3.23+ | Schema 验证 |
| 实时 | SSE | native | 进度推送 |
| 图表 | Recharts | latest | 数据可视化 |
| 测试 | Vitest + Playwright | latest | 全覆盖 |
| 部署 | Vercel Pro | latest | Edge、ISR |
| 监控 | Vercel Analytics + Sentry | latest | 性能追踪 |

---

## 十、实施路线图（更新版）

### 第一阶段：基础设施（2-3周）
Turborepo Monorepo → Next.js 14 + Tailwind → FastAPI + Uvicorn → PostgreSQL 16 主从 → Qdrant → Redis → RabbitMQ → Prometheus + Grafana

### 第二阶段：核心功能（4-5周）
tRPC 类型安全 API → JD生成器（图6）→ 知识库问答（图1+RAG）→ AI初筛（图2+图4）→ vLLM 接入 → 向量检索 → 评估报告

### 第三阶段：商业化（4-6周）
面试安排（图7）→ MCP 工具 → 人才画像（图5）→ 数据报表（图4）→ 数据看板 → Sentry → Vercel Pro 部署

---

*本文档基于7张AI Agent架构图，结合企业级前后端技术栈设计。*
## 七、API 路由设计

### 7.1 后端 API 结构

```
/api/v1/
├── router/
│   └── classify              # POST - 全局意图识别
│
├── agent/                    # 图1 单Agent
│   ├── chat
│   ├── generate-jd           # 页面8（简化版，不走循环）
│   └── knowledge-query       # 页面11
│
├── pipeline/                 # 图2 流水线
│   ├── screen-resume         # 页面4 主流程
│   │   ├── step1-parse-jd
│   │   ├── step2-retrieve
│   │   └── step3-evaluate
│   └── generate-report       # 页面6
│
├── parallel/                 # 图4 Aggregator
│   ├── multi-evaluate        # 人才画像评估
│   └── data-aggregate        # 数据报表合并
│
├── orchestrator/             # 图5 编排器
│   └── complex-analysis      # 复杂综合分析
│
├── loop/                     # 图6 循环
│   └── iterative-generate    # 页面8（完整版，带循环）
│
├── human-loop/               # 图7 人机协作
│   ├── schedule-interview    # 页面5
│   ├── auto-outreach
│   └── human-approve         # 人类确认/拒绝/Stop
│
├── tools/                    # MCP工具
│   ├── email/send
│   ├── calendar/query
│   └── calendar/book
│
├── retrieval/                # 向量检索
│   ├── search
│   └── embed
│
└── memory/                   # 记忆管理
    ├── read
    └── write
```

### 7.2 关键接口详细设计

#### POST /api/v1/pipeline/screen-resume

**请求**：
```json
{
  "jd_text": "高级Java工程师，5年经验，熟悉微服务...",
  "filters": {
    "min_experience": 5,
    "location": "上海",
    "degree": "本科"
  },
  "top_k": 10
}
```

**响应**：
```json
{
  "pipeline_id": "pipe_12345",
  "steps": [
    {
      "step": 1,
      "name": "parse_jd",
      "status": "passed",
      "output": {
        "required_skills": ["Java", "Spring Boot", "微服务"],
        "salary_range": "30-50K",
        "gate_result": "pass"
      }
    },
    {
      "step": 2,
      "name": "retrieve",
      "status": "passed",
      "output": {
        "candidates_found": 15,
        "gate_result": "pass"
      }
    },
    {
      "step": 3,
      "name": "evaluate",
      "status": "completed",
      "output": {
        "top_candidates": [
          {
            "id": "cand_001",
            "name": "张三",
            "match_score": 92,
            "tech_score": 95,
            "culture_score": 85,
            "potential_score": 90,
            "recommendation": "强烈推荐"
          }
        ]
      }
    }
  ],
  "final_output": {
    "recommendations": [...],
    "summary": "找到15名候选人，推荐前10名"
  }
}
```

---

## 八、数据流设计

### 8.1 AI初筛完整数据流

```
[前端页面4: AI初筛]
    ↓ POST /api/v1/pipeline/screen-resume
[API Gateway]
    ↓
[Global Router] 识别意图: "screen_resume"
    ↓ 选择架构: "pipeline"
[Pipeline Engine]
    ↓
Step 1: Parse JD
    - 调用 LLM (Qwen3.6) 提取结构化条件
    - Gate检查: 条件完整性
    - 输出: structured_jd
    ↓
Step 2: Retrieve
    - 调用向量库 (bge-m3嵌入 + 向量搜索)
    - Gate检查: 结果数量+质量
    - 输出: candidate_list
    ↓
Step 3: Evaluate (Aggregator)
    - 并行调用3个LLM:
      * LLM A: 技术能力评估
      * LLM B: 文化契合评估
      * LLM C: 成长潜力评估
    - Aggregator合并加权
    - 输出: ranked_candidates
    ↓
[Response]
    ↓
[前端展示] 候选人卡片 + 匹配度 + 推荐理由
```

---

## 九、实施路线图

### 9.1 三阶段计划

#### 第一阶段：单Agent+MVP（2-3周）
- [ ] 搭建 Next.js 项目框架（/app/* 路由 + Sidebar布局）
- [ ] 实现页面8：JD生成器（图1 单Agent，简化版）
- [ ] 实现页面11：知识库问答（图1 单Agent + RAG）
- [ ] 接入本地模型（omlx + Qwen3.6）
- [ ] **目标**：有2个可演示的AI功能

#### 第二阶段：流水线+核心功能（3-4周）
- [ ] 实现页面4：AI初筛（图2 流水线 + 图4 Aggregator）
- [ ] 搭建向量数据库 + bge-m3嵌入
- [ ] 实现页面6：评估报告
- [ ] 实现页面3：候选人库
- [ ] **目标**：核心功能跑通，可筛选真实简历

#### 第三阶段：高级功能+商业化（4-6周）
- [ ] 实现页面5：面试安排（图7 Human-in-Loop）
- [ ] 接入MCP工具（邮件、日历）
- [ ] 实现页面7：人才画像（图5 Orchestrator）
- [ ] 实现页面9：数据报表（图4 Aggregator）
- [ ] 实现页面1：数据看板
- [ ] 完善页面10：系统设置
- [ ] **目标**：完整SaaS产品，可对外售卖

### 9.2 技术依赖清单

| 组件 | 状态 | 优先级 |
|:---|:---|:---|
| Next.js 14+ (App Router) | 🔄 准备开始 | P0 |
| omlx + Qwen3.6 | ✅ 已配置 | P0 |
| 向量数据库 (Chroma/Pinecone) | 🔄 选型中 | P1 |
| bge-m3 嵌入模型 | ✅ 已学习 | P1 |
| MCP 协议 SDK | 🔄 学习中 | P1 |
| Obsidian 知识库 | ✅ 已搭建 | P2 |
| 邮件服务 (Resend/SendGrid) | ❌ 未开始 | P2 |
| 日历API (Google/Outlook) | ❌ 未开始 | P2 |

---

## 十、风险与对策

| 风险 | 影响 | 对策 |
|:---|:---|:---|
| 本地模型性能不足 | AI响应慢/质量差 | fallback到云端API（GPT-4/Claude） |
| 向量检索不准确 | 匹配候选人质量差 | 调优嵌入模型 + 混合检索（关键词+语义） |
| MCP工具接入复杂 | 面试安排功能延期 | 先用手动确认替代自动化 |
| 成本过高 | 无法商业化 | 本地模型处理80%任务，云端处理复杂任务 |
| 数据隐私 | 候选人信息泄露 | 本地部署优先，数据不出域 |

---

## 十一、附录

### 11.1 七图原文引用

- **图1**：单Agent架构（LLM + Retrieval/Tools/Memory）
- **图2**：流水线架构（LLM Call → Gate → LLM Call → Gate → LLM Call）
- **图3**：路由分发架构（Router → LLM Call 1/2/3 → Out）
- **图4**：聚合器架构（In → 并行LLM Call 1/2/3 → Aggregator → Out）
- **图5**：编排器架构（Orchestrator → 并行LLM Call → Synthesizer → Out）
- **图6**：生成-评估循环（Generator ↔ Evaluator → Accepted/Rejected）
- **图7**：人机协作循环（Human ↔ LLM ↔ Environment + Stop）

### 11.2 术语表

| 术语 | 解释 |
|:---|:---|
| LLM | 大语言模型（如GPT-4、Qwen3.6） |
| RAG | 检索增强生成（Retrieval-Augmented Generation） |
| MCP | 模型上下文协议（Model Context Protocol） |
| Gate | 质检关卡，判断中间产物是否合格 |
| Router | 意图识别分发器 |
| Aggregator | 结果合并器 |
| Orchestrator | 任务编排器 |
| Synthesizer | 结果合成器 |
| omlx | 本地大模型推理框架 |
| bge-m3 | 文本嵌入模型 |
| OTD | Offer到入职时间（招聘效率指标） |

---

*本文档基于7张AI Agent架构图，结合qixia的AI招聘系统需求编写。*


---

# AI 招聘系统 · UI 方案选型

> 基于企业级前后端架构的 UI 设计方案
> 日期：2026-05-23

---

## 一、UI 方案总览

```
┌─────────────────────────────────────────────────────────────┐
│                     设计系统层                               │
│  Design Tokens │ 颜色 │ 字体 │ 间距 │ 圆角 │ 阴影 │ 动画      │
├─────────────────────────────────────────────────────────────┤
│                     组件库层                                 │
│  shadcn/ui (基础) + 自定义业务组件 (招聘专用)                  │
├─────────────────────────────────────────────────────────────┤
│                     页面层                                   │
│  11个业务页面 │ 布局系统 │ 路由架构                            │
├─────────────────────────────────────────────────────────────┤
│                     交互层                                   │
│  实时反馈 │ 动画过渡 │ 加载状态 │ 空状态 │ 错误处理            │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、设计系统选型

### 2.1 为什么选 shadcn/ui + 自定义 Design Tokens？

| 方案 | 优点 | 缺点 | 适用场景 |
|:---|:---|:---|:---|
| **shadcn/ui + 自定义** | 无样式依赖、可完全定制、Radix 可访问性 | 需自己维护 | ✅ **企业级 SaaS** |
| Ant Design | 组件丰富、生态成熟 | 样式难以覆盖、包体积大 | 后台管理 |
| Material UI | Google 设计规范 | 风格固定、定制化难 | 消费级产品 |
| Chakra UI | 简洁、易用 | 组件较少、生态小 | 快速原型 |
| 自研组件库 | 完全可控 | 成本高、周期长 | 大厂专属 |

**shadcn/ui 核心优势**：
- **无 npm 依赖**：组件代码直接复制到项目，完全可控
- **Radix UI 底层**：内置可访问性（ARIA、键盘导航、焦点管理）
- **Tailwind 样式**：原子化 CSS，按需生成，包体积小
- **可深度定制**：任何样式都可覆盖，不受组件库限制

---

### 2.2 Design Tokens 定义

```css
/* globals.css - 设计令牌 */
@layer base {
  :root {
    /* 品牌色 */
    --brand-50:  239 246 255;
    --brand-100: 219 234 254;
    --brand-200: 191 219 254;
    --brand-300: 147 197 253;
    --brand-400: 96  165 250;
    --brand-500: 59  130 246;  /* 主色 */
    --brand-600: 37  99  235;
    --brand-700: 29  78  216;
    --brand-800: 30  64  175;
    --brand-900: 30  58  138;

    /* 语义色 */
    --success-50:  240 253 244;
    --success-500: 34  197 94;
    --success-600: 22  163 74;

    --warning-50:  255 251 235;
    --warning-500: 245 158 11;
    --warning-600: 217 119 6;

    --danger-50:   254 242 242;
    --danger-500:  239 68  68;
    --danger-600:  220 38  38;

    --info-50:     239 246 255;
    --info-500:    59  130 246;

    /* 中性色 */
    --gray-0:   255 255 255;  /* 纯白 */
    --gray-50:  249 250 251;
    --gray-100: 243 244 246;
    --gray-200: 229 231 235;
    --gray-300: 209 213 219;
    --gray-400: 156 163 175;
    --gray-500: 107 114 128;
    --gray-600: 75  85  99;
    --gray-700: 55  65  81;
    --gray-800: 31  41  55;
    --gray-900: 17  24  39;  /* 纯黑 */

    /* 语义变量 */
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;

    /* 间距系统 */
    --space-1: 0.25rem;   /* 4px */
    --space-2: 0.5rem;    /* 8px */
    --space-3: 0.75rem;   /* 12px */
    --space-4: 1rem;      /* 16px */
    --space-5: 1.25rem;   /* 20px */
    --space-6: 1.5rem;    /* 24px */
    --space-8: 2rem;      /* 32px */
    --space-10: 2.5rem;   /* 40px */
    --space-12: 3rem;     /* 48px */
    --space-16: 4rem;     /* 64px */

    /* 字体 */
    --font-sans: "Inter", "PingFang SC", "Microsoft YaHei", sans-serif;
    --font-mono: "JetBrains Mono", "Fira Code", monospace;

    /* 字号 */
    --text-xs: 0.75rem;    /* 12px */
    --text-sm: 0.875rem;   /* 14px */
    --text-base: 1rem;     /* 16px */
    --text-lg: 1.125rem;   /* 18px */
    --text-xl: 1.25rem;    /* 20px */
    --text-2xl: 1.5rem;    /* 24px */
    --text-3xl: 1.875rem;  /* 30px */
    --text-4xl: 2.25rem;   /* 36px */

    /* 阴影 */
    --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
    --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
    --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
    --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);

    /* 动画 */
    --duration-fast: 150ms;
    --duration-normal: 250ms;
    --duration-slow: 350ms;
    --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
    --ease-out: cubic-bezier(0, 0, 0.2, 1);
    --ease-in: cubic-bezier(0.4, 0, 1, 1);
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --popover: 222.2 84% 4.9%;
    --popover-foreground: 210 40% 98%;
    --primary: 210 40% 98%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 212.7 26.8% 83.9%;
  }
}
```

---

## 三、组件库选型

### 3.1 shadcn/ui 基础组件清单

| 组件 | 用途 | 招聘场景 |
|:---|:---|:---|
| **Button** | 按钮 | 提交、确认、取消、导出 |
| **Card** | 卡片 | 候选人卡片、职位卡片、统计卡片 |
| **Dialog** | 弹窗 | 确认操作、详情展示、表单填写 |
| **Dropdown Menu** | 下拉菜单 | 操作菜单、筛选条件 |
| **Input** | 输入框 | 搜索、表单输入 |
| **Textarea** | 文本域 | JD 编辑、备注填写 |
| **Select** | 选择器 | 状态筛选、分类选择 |
| **Tabs** | 标签页 | 候选人详情页、数据报表页 |
| **Table** | 表格 | 候选人列表、职位列表 |
| **Badge** | 徽章 | 状态标签（初筛中、已面试） |
| **Avatar** | 头像 | 候选人头像、面试官头像 |
| **Skeleton** | 骨架屏 | 数据加载占位 |
| **Toast** | 轻提示 | 操作成功/失败反馈 |
| **Tooltip** | 提示 | 图标解释、数据说明 |
| **Progress** | 进度条 | AI 初筛进度、上传进度 |
| **Slider** | 滑块 | 薪资范围选择 |
| **Switch** | 开关 | 功能启用/禁用 |
| **Checkbox** | 复选框 | 批量选择候选人 |
| **Radio Group** | 单选组 | 排序方式、视图切换 |
| **Calendar** | 日历 | 面试日期选择 |
| **Popover** | 浮层 | 筛选面板、快捷操作 |
| **Command** | 命令面板 | 全局搜索、快捷导航 |
| **Sheet** | 侧边抽屉 | 详情展示、表单填写 |
| **Scroll Area** | 滚动区域 | 长列表滚动 |
| **Separator** | 分隔线 | 区域划分 |
| **Collapsible** | 折叠 | 高级筛选条件 |

### 3.2 自定义业务组件（招聘专用）

```typescript
// components/features/screening/candidate-card.tsx
interface CandidateCardProps {
  candidate: Candidate;
  matchScore: number;
  onSelect: (id: string) => void;
  onAction: (action: string) => void;
}

export function CandidateCard({ candidate, matchScore, onSelect, onAction }: CandidateCardProps) {
  return (
    <Card className="hover:shadow-md transition-shadow duration-250">
      <CardHeader className="flex flex-row items-start gap-4">
        <Avatar className="h-12 w-12">
          <AvatarFallback>{candidate.name[0]}</AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base truncate">{candidate.name}</CardTitle>
            <MatchScoreBadge score={matchScore} />
          </div>
          <CardDescription className="line-clamp-1">
            {candidate.currentCompany} · {candidate.experienceYears}年 · {candidate.location}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-1.5">
          {candidate.skills.slice(0, 5).map(skill => (
            <Badge key={skill} variant="secondary" className="text-xs">{skill}</Badge>
          ))}
        </div>
        <ScoreRadar scores={candidate.aiScores} className="mt-4" />
      </CardContent>
      <CardFooter className="flex justify-between">
        <Button variant="ghost" size="sm" onClick={() => onSelect(candidate.id)}>
          查看详情
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">操作</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onClick={() => onAction('interview')}>安排面试</DropdownMenuItem>
            <DropdownMenuItem onClick={() => onAction('reject')}>淘汰</DropdownMenuItem>
            <DropdownMenuItem onClick={() => onAction('save')}>收藏</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardFooter>
    </Card>
  );
}
```

```typescript
// components/features/screening/match-score-badge.tsx
interface MatchScoreBadgeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
}

export function MatchScoreBadge({ score, size = 'md' }: MatchScoreBadgeProps) {
  const variant = score >= 85 ? 'success' : score >= 70 ? 'warning' : 'danger';
  const colors = {
    success: 'bg-success-50 text-success-600 border-success-200',
    warning: 'bg-warning-50 text-warning-600 border-warning-200',
    danger: 'bg-danger-50 text-danger-600 border-danger-200',
  };

  return (
    <div className={cn(
      "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-semibold",
      colors[variant],
      size === 'sm' && 'text-xs',
      size === 'md' && 'text-sm',
      size === 'lg' && 'text-base',
    )}>
      <Star className={cn("fill-current", size === 'sm' ? 'h-3 w-3' : 'h-4 w-4')} />
      {score}%
    </div>
  );
}
```

```typescript
// components/features/screening/pipeline-status.tsx
interface PipelineStatusProps {
  steps: PipelineStep[];
  currentStep: number;
}

export function PipelineStatus({ steps, currentStep }: PipelineStatusProps) {
  return (
    <div className="space-y-3">
      {steps.map((step, index) => (
        <div key={index} className="flex items-center gap-3">
          <div className={cn(
            "flex h-8 w-8 items-center justify-center rounded-full border-2",
            index < currentStep && "border-brand-500 bg-brand-50 text-brand-600",
            index === currentStep && "border-brand-500 bg-brand-500 text-white animate-pulse",
            index > currentStep && "border-gray-200 text-gray-400",
          )}>
            {index < currentStep ? <Check className="h-4 w-4" /> : <span className="text-sm">{index + 1}</span>}
          </div>
          <div className="flex-1">
            <p className={cn("text-sm font-medium", index > currentStep && "text-gray-400")}>
              {step.name}
            </p>
            {step.gateResult && (
              <p className={cn("text-xs", 
                step.gateResult === 'pass' ? 'text-success-600' : 'text-danger-600'
              )}>
                Gate: {step.gateResult === 'pass' ? '通过' : '未通过'}
              </p>
            )}
          </div>
          {index === currentStep && <Loader2 className="h-4 w-4 animate-spin text-brand-500" />}
        </div>
      ))}
    </div>
  );
}
```

```typescript
// components/features/report/score-radar.tsx
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';

interface ScoreRadarProps {
  scores: { tech: number; culture: number; potential: number };
  className?: string;
}

export function ScoreRadar({ scores, className }: ScoreRadarProps) {
  const data = [
    { subject: '技术能力', A: scores.tech, fullMark: 100 },
    { subject: '文化契合', A: scores.culture, fullMark: 100 },
    { subject: '成长潜力', A: scores.potential, fullMark: 100 },
    { subject: '沟通能力', A: scores.tech * 0.8, fullMark: 100 },
    { subject: '稳定性', A: scores.culture * 0.9, fullMark: 100 },
  ];

  return (
    <div className={cn("h-[200px] w-full", className)}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
          <PolarGrid stroke="hsl(var(--border))" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} />
          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
          <Radar
            name="候选人"
            dataKey="A"
            stroke="hsl(var(--brand-500))"
            fill="hsl(var(--brand-500))"
            fillOpacity={0.2}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

## 四、布局系统

### 4.1 整体布局架构

```
┌─────────────────────────────────────────────────────────────┐
│  Header (固定)                                               │
│  Logo │ 全局搜索 │ 通知 │ 用户头像                            │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                    │
│ Sidebar  │              Main Content                          │
│ (可折叠)  │                                                    │
│          │  ┌─────────────────────────────────────────────┐   │
│ 导航菜单  │  │  Page Header                                  │   │
│          │  │  标题 │ 面包屑 │ 操作按钮                        │   │
│          │  ├─────────────────────────────────────────────┤   │
│          │  │                                             │   │
│          │  │              Content Area                     │   │
│          │  │                                             │   │
│          │  │                                             │   │
│          │  └─────────────────────────────────────────────┘   │
│          │                                                    │
└──────────┴──────────────────────────────────────────────────┘
```

### 4.2 路由组设计（App Router）

```typescript
// app/(dashboard)/layout.tsx - 工作台布局
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}

// app/(dashboard)/screening/page.tsx
// app/(dashboard)/interview/page.tsx
// app/(dashboard)/report/page.tsx
// ... 11个页面

// app/(auth)/layout.tsx - 认证页布局（无 Sidebar）
// app/(marketing)/layout.tsx - 官网布局
```

### 4.3 11 页面布局映射

| 页面 | 布局特点 | 核心交互 |
|:---|:---|:---|
| **数据看板** | 网格卡片 + 图表 | 实时数据刷新 |
| **职位管理** | 表格 + 侧边抽屉 | CRUD 操作 |
| **候选人库** | 瀑布流/表格切换 | 筛选、排序、批量操作 |
| **AI初筛** | 左右分栏 | 实时流水线进度 |
| **面试安排** | 日历视图 + 列表 | 拖拽排期 |
| **评估报告** | 详情页 + 雷达图 | 评分、批注 |
| **人才画像** | 时间轴 + 能力模型 | 多维度分析 |
| **JD生成器** | 编辑器 + 预览 | AI 生成、迭代优化 |
| **数据报表** | 图表组合 + 导出 | 筛选维度切换 |
| **系统设置** | 表单分组 | 配置保存 |
| **知识库** | 树形导航 + 搜索 | 文档编辑 |

---

## 五、交互设计

### 5.1 加载状态设计

```typescript
// 骨架屏（首屏加载）
<Skeleton className="h-[200px] w-full" />

// 按钮加载（操作提交）
<Button disabled={isLoading}>
  {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
  提交
</Button>

// 页面加载（路由切换）
<Suspense fallback={<PageSkeleton />}>
  <PageContent />
</Suspense>

// 流水线进度（AI初筛）
<PipelineStatus steps={steps} currentStep={currentStep} />
```

### 5.2 空状态设计

```typescript
// EmptyState 组件
interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: { label: string; onClick: () => void };
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="rounded-full bg-muted p-4 mb-4">
        {icon}
      </div>
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="text-sm text-muted-foreground mt-1 max-w-sm">{description}</p>
      {action && (
        <Button className="mt-4" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}

// 使用示例
<EmptyState
  icon={<Search className="h-8 w-8 text-muted-foreground" />}
  title="暂无匹配候选人"
  description="当前筛选条件下没有找到合适的候选人，建议放宽条件或优化 JD 描述。"
  action={{ label: '放宽条件', onClick: () => setFilters({}) }}
/>
```

### 5.3 错误处理设计

```typescript
// ErrorBoundary 组件
export function ErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  return (
    <div className="flex flex-col items-center justify-center p-8">
      <AlertCircle className="h-12 w-12 text-destructive mb-4" />
      <h2 className="text-lg font-semibold">出错了</h2>
      <p className="text-sm text-muted-foreground mt-1 mb-4">
        {error.message || '未知错误，请稍后重试'}
      </p>
      <div className="flex gap-2">
        <Button variant="outline" onClick={() => window.location.reload()}>
          刷新页面
        </Button>
        <Button onClick={resetErrorBoundary}>
          重试
        </Button>
      </div>
    </div>
  );
}

// Toast 错误提示
toast.error('操作失败', {
  description: '无法连接到服务器，请检查网络后重试。',
  action: { label: '重试', onClick: () => retry() },
});
```

### 5.4 动画设计

```css
/* 页面过渡 */
.page-transition-enter {
  opacity: 0;
  transform: translateY(10px);
}
.page-transition-enter-active {
  opacity: 1;
  transform: translateY(0);
  transition: opacity 300ms, transform 300ms;
}

/* 列表项进入 */
.list-item-enter {
  opacity: 0;
  transform: scale(0.95);
}
.list-item-enter-active {
  opacity: 1;
  transform: scale(1);
  transition: opacity 200ms, transform 200ms;
}

/* 骨架屏脉冲 */
@keyframes skeleton-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.skeleton {
  animation: skeleton-pulse 2s ease-in-out infinite;
}
```

---

## 六、响应式设计

### 6.1 断点定义

```typescript
// tailwind.config.ts
const config = {
  theme: {
    screens: {
      'sm': '640px',   // 手机横屏
      'md': '768px',   // 平板
      'lg': '1024px',  // 小桌面
      'xl': '1280px',  // 标准桌面
      '2xl': '1536px', // 大桌面
    },
  },
};
```

### 6.2 布局适配

| 设备 | Sidebar | Content | 操作方式 |
|:---|:---|:---|:---|
| **桌面 (>1024px)** | 展开 240px | 完整表格/图表 | 鼠标 hover、右键菜单 |
| **平板 (768-1024px)** | 折叠 64px | 卡片布局 | 点击展开、手势滑动 |
| **手机 (<768px)** | 隐藏（汉堡菜单） | 单列列表 | 点击、长按、底部操作栏 |

---

## 七、主题与深色模式

### 7.1 主题切换

```typescript
// components/theme-provider.tsx
import { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'dark' | 'light' | 'system';

const ThemeProviderContext = createContext<{ theme: Theme; setTheme: (theme: Theme) => void } | undefined>(undefined);

export function ThemeProvider({ children, defaultTheme = 'system' }: { children: React.ReactNode; defaultTheme?: Theme }) {
  const [theme, setTheme] = useState<Theme>(defaultTheme);

  useEffect(() => {
    const root = window.document.documentElement;
    root.classList.remove('light', 'dark');

    if (theme === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      root.classList.add(systemTheme);
    } else {
      root.classList.add(theme);
    }
  }, [theme]);

  return (
    <ThemeProviderContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeProviderContext.Provider>
  );
}

export const useTheme = () => {
  const context = useContext(ThemeProviderContext);
  if (!context) throw new Error('useTheme must be used within a ThemeProvider');
  return context;
};
```

### 7.2 深色模式适配要点

| 元素 | Light | Dark |
|:---|:---|:---|
| 背景 | white | gray-900 |
| 卡片 | white | gray-800 |
| 文字主色 | gray-900 | gray-100 |
| 文字次色 | gray-500 | gray-400 |
| 边框 | gray-200 | gray-700 |
| 品牌色 | brand-500 | brand-400 |
| 成功色 | success-500 | success-400 |
| 图表网格 | gray-200 | gray-700 |
| 阴影 | shadow-md | shadow-lg（更亮） |

---

## 八、图标系统

### 8.1 图标选型：Lucide React

**为什么不是 Ant Design Icons / FontAwesome？**

| 方案 | 优点 | 缺点 | 选择 |
|:---|:---|:---|:---|
| **Lucide** | 轻量、现代、Tree-shaking | 数量较少 | ✅ **最佳** |
| Ant Design Icons | 丰富、风格统一 | 包体积大 | ❌ |
| FontAwesome | 极丰富 | 需配置、体积大 | ❌ |
| Heroicons | 简洁、Tailwind 友好 | 数量较少 | ⚠️ 备选 |

```typescript
// 图标使用示例
import { 
  Search, Filter, Download, Upload, Plus, Trash2, Edit, 
  CheckCircle, XCircle, Clock, Star, Mail, Calendar, 
  ChevronDown, ChevronRight, MoreHorizontal, Loader2,
  LayoutDashboard, Users, Briefcase, FileText, Settings,
  Bell, User, LogOut, Menu, X, ArrowLeft, ArrowRight
} from 'lucide-react';

// 侧边栏导航图标映射
const navIcons = {
  dashboard: LayoutDashboard,
  jobs: Briefcase,
  candidates: Users,
  screening: Search,
  interview: Calendar,
  report: FileText,
  settings: Settings,
};
```

---

## 九、字体系统

### 9.1 字体选型

| 用途 | 字体 | 理由 |
|:---|:---|:---|
| **英文/数字** | Inter | 现代、清晰、开源、优化屏幕显示 |
| **中文** | PingFang SC / Microsoft YaHei | 系统字体，无需加载 |
| **代码** | JetBrains Mono | 等宽、易读、区分相似字符 |

```css
/* tailwind.config.ts */
fontFamily: {
  sans: ['Inter', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
  mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
}
```

### 9.2 字体加载策略

```html
<!-- layout.tsx -->
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

---

## 十、UI 依赖清单

```json
{
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "typescript": "^5.4.0",

    "tailwindcss": "^3.4.0",
    "@tailwindcss/typography": "^0.5.0",
    "tailwind-merge": "^2.2.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",

    "@radix-ui/react-accordion": "^1.2.0",
    "@radix-ui/react-alert-dialog": "^1.0.0",
    "@radix-ui/react-avatar": "^1.0.0",
    "@radix-ui/react-checkbox": "^1.0.0",
    "@radix-ui/react-collapsible": "^1.0.0",
    "@radix-ui/react-dialog": "^1.0.0",
    "@radix-ui/react-dropdown-menu": "^2.0.0",
    "@radix-ui/react-hover-card": "^1.0.0",
    "@radix-ui/react-label": "^2.0.0",
    "@radix-ui/react-menubar": "^1.0.0",
    "@radix-ui/react-navigation-menu": "^1.0.0",
    "@radix-ui/react-popover": "^1.0.0",
    "@radix-ui/react-progress": "^1.0.0",
    "@radix-ui/react-radio-group": "^1.0.0",
    "@radix-ui/react-scroll-area": "^1.0.0",
    "@radix-ui/react-select": "^2.0.0",
    "@radix-ui/react-separator": "^1.0.0",
    "@radix-ui/react-slider": "^1.0.0",
    "@radix-ui/react-switch": "^1.0.0",
    "@radix-ui/react-tabs": "^1.0.0",
    "@radix-ui/react-toast": "^1.0.0",
    "@radix-ui/react-toggle": "^1.0.0",
    "@radix-ui/react-tooltip": "^1.0.0",

    "lucide-react": "^0.378.0",
    "recharts": "^2.12.0",
    "framer-motion": "^11.0.0",

    "@tanstack/react-query": "^5.0.0",
    "@trpc/client": "^11.0.0",
    "@trpc/react-query": "^11.0.0",
    "zustand": "^4.5.0",
    "zod": "^3.23.0",
    "react-hook-form": "^7.51.0",
    "@hookform/resolvers": "^3.3.0",
    "date-fns": "^3.6.0",
    "react-day-picker": "^8.10.0",
    "cmdk": "^1.0.0",
    "vaul": "^0.9.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss-animate": "^1.0.0"
  }
}
```

---

*本文档基于企业级技术架构，为 AI 招聘系统提供完整的 UI 方案选型。*
