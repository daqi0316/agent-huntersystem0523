# AI招聘Agent: 上下文-记忆架构设计

基于HelloAgents Chapter 8(记忆与检索) + Chapter 9(上下文工程),结合现有6-Agent多Agent架构,设计完整的上下文-记忆驱动架构.

---

## 一、整体架构概览

```
+-----------------------------------------------------------------------------+
|                           编排层 (Orchestrator)                              |
|                    统一入口 / 任务分发 / 结果聚合 / 记忆协调                     |
|                                                                              |
|   +---------------------------------------------------------------------+   |
|   |  ContextBuilder (GSSC流水线)                                        |   |
|   |  +--------+  +--------+  +----------+  +---------+               |   |
|   |  | Gather |->| Select |->| Structure|->| Compress|               |   |
|   |  +--------+  +--------+  +----------+  +---------+               |   |
|   |       ^              ^                    ^                        |   |
|   |       +--------------+--------------------+                        |   |
|   |              从MemoryManager + RAGPipeline获取                      |   |
|   +---------------------------------------------------------------------+   |
|                                                                              |
|   +---------------------------------------------------------------------+   |
|   |  MemoryManager (四层记忆系统)                                        |   |
|   |  +--------------+  +--------------+  +--------------+              |   |
|   |  | WorkingMemory|  |EpisodicMemory|  |SemanticMemory|              |   |
|   |  | 当前对话状态  |  | 招聘事件序列  |  | 人才知识图谱  |              |   |
|   |  |  (TTL: 30min)|  | (SQLite+向量) |  |(Qdrant+Neo4j)|              |   |
|   |  +--------------+  +--------------+  +--------------+              |   |
|   |  +--------------------------------------------------------------+   |   |
|   |  | PerceptualMemory (简历PDF/图片/语音面试录音)                    |   |   |
|   |  |                    (多模态向量存储)                             |   |   |
|   |  +--------------------------------------------------------------+   |   |
|   +---------------------------------------------------------------------+   |
|                                                                              |
|   +---------------------------------------------------------------------+   |
|   |  RAGPipeline (招聘知识库)                                            |   |
|   |  +-------------+  +-------------+  +-------------+                |   |
|   |  | 岗位JD库    |  | 面试题库    |  | 公司制度库  |                |   |
|   |  | (向量检索)  |  | (向量检索)  |  | (向量检索)  |                |   |
|   |  +-------------+  +-------------+  +-------------+                |   |
|   |  +-------------+  +-------------+                                  |   |
|   |  | 行业薪酬库  |  | 法律法规库  |                                  |   |
|   |  | (向量检索)  |  | (向量检索)  |                                  |   |
|   |  +-------------+  +-------------+                                  |   |
|   +---------------------------------------------------------------------+   |
+-----------------------------------------------------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------------+
|                           专业Agent层 (6个)                                  |
+-----------------------------------------------------------------------------+
|                                                                              |
|  +-------------+  +-------------+  +-------------+                        |
|  | 寻访Agent   |  | 筛选Agent   |  | 面试Agent   |                        |
|  | Prompt-B    |  | Prompt-C    |  | Prompt-D    |                        |
|  |             |  |             |  |             |                        |
|  | 上下文需求: |  | 上下文需求: |  | 上下文需求: |                        |
|  | - 岗位画像  |  | - 简历内容  |  | - 面试题库  |                        |
|  | - 历史寻访  |  | - 硬性要求  |  | - 候选人档案|                        |
|  | - 人才地图  |  | - 匹配规则  |  | - 过往评价  |                        |
|  |             |  |             |  |             |                        |
|  | 记忆写入:   |  | 记忆写入:   |  | 记忆写入:   |                        |
|  | - 寻访记录  |  | - 筛选结果  |  | - 面试评价  |                        |
|  | - 渠道效果  |  | - 匹配分数  |  | - 能力评估  |                        |
|  +-------------+  +-------------+  +-------------+                        |
|                                                                              |
|  +-------------+  +-------------+  +-------------+                        |
|  | 薪酬Agent   |  | 入职Agent   |  | 数据Agent   |                        |
|  | Prompt-E    |  | Prompt-F    |  | Prompt-G    |                        |
|  |             |  |             |  |             |                        |
|  | 上下文需求: |  | 上下文需求: |  | 上下文需求: |                        |
|  | - 薪酬基准  |  | - 入职清单  |  | - 全链路数据|                        |
|  | - 候选人期望|  | - 历史入职  |  | - 各Agent记忆|                       |
|  | - 公司预算  |  | - 培训计划  |  | - 效能指标  |                        |
|  |             |  |             |  |             |                        |
|  | 记忆写入:   |  | 记忆写入:   |  | 记忆写入:   |                        |
|  | - 谈判记录  |  | - 入职状态  |  | - 分析结论  |                        |
|  | - 最终Offer |  | - 问题跟踪  |  | - 优化建议  |                        |
|  +-------------+  +-------------+  +-------------+                        |
|                                                                              |
+-----------------------------------------------------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------------+
|                           共享基础设施层                                      |
|                                                                              |
|   +-------------+  +-------------+  +-------------+  +-------------+     |
|   | NoteTool    |  |TerminalTool |  | 工具注册表  |  | 安全策略    |     |
|   | 结构化笔记  |  | 文件系统操作|  | ToolRegistry|  | 审批流程    |     |
|   | (进度追踪)  |  | (简历解析)  |  |             |  |             |     |
|   +-------------+  +-------------+  +-------------+  +-------------+     |
|                                                                              |
|   +---------------------------------------------------------------------+   |
|   | 嵌入服务 (EmbeddingService)                                         |   |
|   | - 简历向量化 (bge-m3 / text-embedding-v3)                           |   |
|   | - JD向量化                                                          |   |
|   | - 面试评价向量化                                                    |   |
|   +---------------------------------------------------------------------+   |
|                                                                              |
+-----------------------------------------------------------------------------+
```

---

## 二、记忆系统映射(招聘场景)

将第八章的四层记忆系统映射到招聘场景:

| 记忆类型 | 人类记忆类比 | 招聘场景映射 | 存储后端 | TTL/持久性 |
|---------|-----------|-----------|---------|-----------|
| **WorkingMemory** | 工作记忆(当前注意) | 当前对话轮次、正在处理的候选人、当前岗位JD | 纯内存+Redis | 30分钟TTL |
| **EpisodicMemory** | 情景记忆(个人经历) | 某候选人的完整招聘事件链:投递->筛选通过->面试->Offer->入职 | SQLite+Qdrant | 永久 |
| **SemanticMemory** | 语义记忆(通用知识) | 人才画像图谱、技能关系网、公司组织架构、薪酬等级 | Qdrant+Neo4j | 永久 |
| **PerceptualMemory** | 感知记忆(感官印象) | 简历PDF内容、候选人照片、面试录音转写、代码测试截图 | SQLite+Qdrant | 永久 |

---

## 三、上下文构建策略(按Agent定制)

每个专业Agent的上下文需求不同,ContextBuilder的GSSC流水线需要**按Agent类型定制Select策略**.

### 3.1 寻访Agent上下文模板

```
[Role & Policies]
你是资深招聘顾问,擅长人才寻访和渠道运营.
优先使用内部人才库,其次考虑外部渠道.

[Task]
为{岗位名称}寻访合适的候选人,目标{人数}人.

[Evidence] <- 从RAG检索
- 岗位JD详细要求(技能、经验、薪资范围)
- 公司介绍和文化关键词
- 行业人才地图(从SemanticMemory图谱)

[Context] <- 从Memory检索
- 该岗位历史寻访记录(EpisodicMemory)
- 相似岗位的成功案例
- 当前活跃候选人列表(WorkingMemory)

[Output]
输出候选人推荐列表,包含匹配理由和渠道来源.
```

### 3.2 筛选Agent上下文模板

```
[Role & Policies]
你是简历筛选专家,严格按硬性条件过滤,软性条件标注.

[Task]
筛选{候选人姓名}的简历,判断是否进入下一轮.

[Evidence] <- 从RAG检索
- 岗位硬性要求清单(学历、年限、技能)
- 公司招聘政策(如内推优先、校招流程)

[Context] <- 从Memory检索
- 该候选人历史投递记录(EpisodicMemory)
- 该岗位已筛选通过的候选人画像(用于横向对比)
- 简历原始内容(PerceptualMemory解析结果)

[Output]
输出:通过/不通过 + 匹配分数 + 关键亮点/风险点.
```

### 3.3 面试Agent上下文模板

```
[Role & Policies]
你是技术面试官,使用STAR法则评估候选人.
每轮面试后必须输出结构化评价.

[Task]
为{候选人}设计并执行{岗位}的技术面试.

[Evidence] <- 从RAG检索
- 岗位面试题库(按技能点分类)
- 公司面试评分标准
- 行业技术趋势(用于追问)

[Context] <- 从Memory检索
- 候选人简历亮点(PerceptualMemory解析)
- 前几轮面试评价(EpisodicMemory事件链)
- 该岗位历史面试常见问题(SemanticMemory归纳)

[Output]
输出:面试问题列表 + 候选人回答摘要 + 结构化评价表.
```

---

## 四、跨Agent记忆流转机制

招聘流程是**有向流水线**,记忆需要在Agent间流转:

```
寻访Agent
   |
   v 写入EpisodicMemory
{"event": "candidate_sourced", "candidate_id": "C001",
 "channel": "boss", "job_id": "J001", "timestamp": "..."}
   |
   v 触发Orchestrator记忆协调
Orchestrator检测到新候选人,通知筛选Agent
   |
   v 筛选Agent读取记忆
筛选Agent从EpisodicMemory读取C001的寻访记录
从PerceptualMemory读取简历解析结果
   |
   v 筛选Agent写入记忆
{"event": "candidate_screened", "candidate_id": "C001",
 "result": "passed", "score": 85, "highlights": [...]}
   |
   v 触发Orchestrator记忆协调
Orchestrator检测到筛选通过,通知面试Agent
   |
   v 面试Agent读取记忆
面试Agent读取C001的完整事件链(寻访->筛选)
从SemanticMemory读取技能图谱(用于设计针对性问题)
   |
   v ... 以此类推,直到入职Agent
   |
   v 入职Agent写入记忆
{"event": "candidate_onboarded", "candidate_id": "C001",
 "offer_accepted": true, "start_date": "2026-06-15"}
   |
   v 数据Agent读取全链路记忆
数据Agent聚合C001的完整招聘周期数据,生成分析报告
同时更新SemanticMemory(如:该渠道该岗位的转化率)

=======================================================================
关键设计:每个Agent只读写与自己相关的记忆片段,Orchestrator负责协调流转
=======================================================================
```

---

## 五、NoteTool进度追踪(招聘专用)

### 5.1 岗位项目笔记 (project_note)

```yaml
---
id: job_J001_2026
title: "高级Python工程师招聘"
type: project
tags: [job_J001, backend, python, urgent]
created_at: 2026-05-20T10:00:00
updated_at: 2026-05-29T15:14:00
status: active  # active | paused | closed
---

## 岗位画像
- 职级: P6
- 技能: Python, FastAPI, PostgreSQL, Redis
- 年限: 3-5年
- 薪资范围: 25K-35K

## 招聘漏斗
| 阶段 | 目标 | 当前 | 转化率 |
|------|------|------|--------|
| 寻访 | 50 | 47 | - |
| 筛选通过 | 25 | 22 | 47% |
| 初面通过 | 15 | 12 | 55% |
| 终面通过 | 8 | 5 | 42% |
| Offer接受 | 5 | 3 | 60% |
| 入职 | 5 | 2 | - |

## 活跃候选人 (WorkingMemory同步)
- C001: 终面通过,等待Offer
- C002: 初面安排中 (6月2日)
- C003: 筛选通过,待初面

## 阻塞项
- [blocker] C001期望薪资35K,超出预算上限
- [blocker] 终面面试官出差,延迟1周

## 关键决策记录
- 2026-05-25: 放宽Redis要求,接受Memcached经验
- 2026-05-28: 启动内推奖励计划
```

### 5.2 候选人档案笔记 (candidate_note)

```yaml
---
id: candidate_C001
title: "候选人: 张三"
type: candidate
tags: [candidate_C001, job_J001, python, backend]
created_at: 2026-05-22T14:00:00
updated_at: 2026-05-29T15:14:00
---

## 基本信息
- 姓名: 张三
- 电话: 138****8888
- 邮箱: zhangsan@example.com
- 当前状态: 终面通过

## 招聘事件链 (EpisodicMemory索引)
1. [2026-05-22] 寻访: Boss直聘投递
2. [2026-05-23] 筛选: 通过 (匹配分: 85)
3. [2026-05-25] 初面: 通过 (技术分: 88, 沟通分: 82)
4. [2026-05-28] 终面: 通过 (架构分: 90, 文化分: 85)

## 能力评估 (SemanticMemory关联)
- Python: 精通 (算法题满分)
- FastAPI: 熟练 (有生产经验)
- PostgreSQL: 一般 (基础CRUD,缺少优化经验)
- 软技能: 沟通清晰,主动性高

## 薪酬谈判记录
- 候选人期望: 35K (13薪)
- 公司预算: 32K (14薪)
- 当前差距: 3K/月
- 谈判策略: 用14薪+期权弥补

## 下一步行动
- [ ] HR发起Offer审批
- [ ] 准备期权方案说明
```

---

## 六、核心代码框架

### 6.1 招聘专用记忆配置

```python
from dataclasses import dataclass
from typing import Dict


@dataclass
class RecruitmentMemoryConfig:
    """招聘场景记忆配置"""
    # WorkingMemory: 当前活跃候选人的TTL
    working_ttl_seconds: int = 1800  # 30分钟

    # EpisodicMemory: 事件链保留数量
    max_episodes_per_candidate: int = 50

    # SemanticMemory: 技能图谱更新频率
    skill_graph_update_interval: int = 86400  # 24小时

    # RAG: 各知识库命名空间
    rag_namespaces: Dict[str, str] = None

    def __post_init__(self):
        if self.rag_namespaces is None:
            self.rag_namespaces = {
                "job_descriptions": "jd_kb",
                "interview_questions": "interview_kb",
                "company_policies": "policy_kb",
                "salary_benchmark": "salary_kb",
                "legal_compliance": "legal_kb"
            }
```

### 6.2 招聘Orchestrator

```python
from typing import Dict, List, Optional
from datetime import datetime
import json


class RecruitmentOrchestrator:
    """
    招聘编排器:协调6个专业Agent + 管理记忆流转
    """

    AGENT_TYPES = [
        "sourcing",      # 寻访
        "screening",     # 筛选
        "interview",     # 面试
        "offering",      # 薪酬
        "onboarding",    # 入职
        "analytics"      # 数据分析
    ]

    def __init__(self, config: RecruitmentMemoryConfig):
        self.config = config

        # 初始化记忆系统 (Chapter 8)
        self.memory_manager = MemoryManager()
        self.working_memory = WorkingMemory(ttl=config.working_ttl_seconds)
        self.episodic_memory = EpisodicMemory()
        self.semantic_memory = SemanticMemory()
        self.perceptual_memory = PerceptualMemory()

        # 初始化RAG (Chapter 8)
        self.rag_pipeline = RAGPipeline()

        # 初始化上下文构建器 (Chapter 9)
        self.context_builder = ContextBuilder(
            memory_tool=self._create_memory_tool(),
            rag_tool=self._create_rag_tool(),
            config=ContextConfig(max_tokens=4000)
        )

        # 初始化笔记系统 (Chapter 9)
        self.note_tool = NoteTool(workspace="./recruitment_notes")

        # 初始化专业Agent
        self.agents = {
            agent_type: self._create_agent(agent_type)
            for agent_type in self.AGENT_TYPES
        }

        # 候选人状态机
        self.candidate_states: Dict[str, str] = {}

    def _create_memory_tool(self) -> MemoryTool:
        """创建招聘专用记忆工具"""
        return MemoryTool(
            user_id="recruitment_system",
            working_memory=self.working_memory,
            episodic_memory=self.episodic_memory,
            semantic_memory=self.semantic_memory
        )

    def _create_rag_tool(self) -> RAGTool:
        """创建招聘专用RAG工具"""
        return RAGTool(
            knowledge_base_path="./recruitment_kb",
            namespaces=self.config.rag_namespaces
        )

    def _create_agent(self, agent_type: str) -> "RecruitmentAgent":
        """创建特定类型的招聘Agent"""
        prompts = {
            "sourcing": self._sourcing_prompt(),
            "screening": self._screening_prompt(),
            "interview": self._interview_prompt(),
            "offering": self._offering_prompt(),
            "onboarding": self._onboarding_prompt(),
            "analytics": self._analytics_prompt()
        }

        return RecruitmentAgent(
            agent_type=agent_type,
            system_prompt=prompts[agent_type],
            context_builder=self.context_builder,
            memory_manager=self.memory_manager,
            note_tool=self.note_tool
        )

    def process(self, task: Dict) -> Dict:
        """
        主入口:处理招聘任务

        Args:
            task: {
                "type": "sourcing|screening|interview|...",
                "job_id": "J001",
                "candidate_id": "C001",  # 可选
                "data": {...}  # 任务特定数据
            }
        """
        agent_type = task["type"]
        agent = self.agents[agent_type]

        # 1. 构建该Agent的专用上下文
        context = self._build_agent_context(agent_type, task)

        # 2. 执行Agent
        result = agent.run(context, task)

        # 3. 写入记忆
        self._write_memories(agent_type, task, result)

        # 4. 更新笔记
        self._update_notes(agent_type, task, result)

        # 5. 触发状态流转
        self._trigger_state_transition(task, result)

        return result

    def _build_agent_context(self, agent_type: str, task: Dict) -> str:
        """为特定Agent构建最优上下文"""

        # 根据Agent类型定制Gather策略
        if agent_type == "sourcing":
            custom_packets = [
                self._gather_job_profile(task["job_id"]),
                self._gather_sourcing_history(task["job_id"]),
                self._gather_talent_map()
            ]
        elif agent_type == "screening":
            custom_packets = [
                self._gather_resume(task.get("candidate_id")),
                self._gather_job_requirements(task["job_id"]),
                self._gather_candidate_history(task.get("candidate_id"))
            ]
        elif agent_type == "interview":
            custom_packets = [
                self._gather_interview_questions(task["job_id"]),
                self._gather_candidate_profile(task["candidate_id"]),
                self._gather_previous_evaluations(task["candidate_id"])
            ]
        elif agent_type == "offering":
            custom_packets = [
                self._gather_salary_benchmark(task["job_id"]),
                self._gather_candidate_expectation(task["candidate_id"]),
                self._gather_company_budget(task["job_id"])
            ]
        elif agent_type == "onboarding":
            custom_packets = [
                self._gather_onboarding_checklist(),
                self._gather_onboarding_history(task.get("candidate_id")),
                self._gather_training_plan(task["job_id"])
            ]
        elif agent_type == "analytics":
            custom_packets = [
                self._gather_funnel_data(task.get("job_id")),
                self._gather_all_agent_memories(task.get("candidate_id")),
                self._gather_industry_benchmark()
            ]

        # 使用ContextBuilder构建最终上下文
        return self.context_builder.build(
            user_query=task.get("instruction", f"Execute {agent_type} task"),
            system_instructions=self._get_system_prompt(agent_type),
            custom_packets=custom_packets
        )

    def _write_memories(self, agent_type: str, task: Dict, result: Dict):
        """将Agent执行结果写入记忆系统"""

        # 写入WorkingMemory(当前活跃状态)
        self.working_memory.add(
            content=f"{agent_type} completed for {task.get('candidate_id', 'N/A')}",
            metadata={"agent_type": agent_type, "task": task, "result": result}
        )

        # 写入EpisodicMemory(事件序列)
        if task.get("candidate_id"):
            self.episodic_memory.add(
                content=json.dumps({
                    "event_type": f"{agent_type}_completed",
                    "candidate_id": task["candidate_id"],
                    "job_id": task["job_id"],
                    "result_summary": result.get("summary", ""),
                    "timestamp": datetime.now().isoformat()
                }),
                memory_type="episodic",
                importance=self._calculate_importance(result)
            )

        # 写入SemanticMemory(知识提取)
        if agent_type == "interview" and "skill_evaluation" in result:
            for skill, level in result["skill_evaluation"].items():
                self.semantic_memory.add(
                    content=f"Candidate {task['candidate_id']} skill {skill}: {level}",
                    memory_type="semantic"
                )

    def _update_notes(self, agent_type: str, task: Dict, result: Dict):
        """更新结构化笔记"""
        if task.get("job_id"):
            self._update_job_note(task["job_id"], agent_type, result)
        if task.get("candidate_id"):
            self._update_candidate_note(task["candidate_id"], agent_type, result)

    def _trigger_state_transition(self, task: Dict, result: Dict):
        """触发候选人状态流转"""
        candidate_id = task.get("candidate_id")
        if not candidate_id:
            return

        current_state = self.candidate_states.get(candidate_id, "new")

        # 状态机转换
        transitions = {
            "new": {"sourcing": "sourced"},
            "sourced": {"screening": "screened"},
            "screened": {"interview": "interviewing"},
            "interviewing": {"interview": "interviewed"},
            "interviewed": {"offering": "offering"},
            "offering": {"offering": "offered"},
            "offered": {"onboarding": "onboarding"},
            "onboarding": {"onboarding": "onboarded"}
        }

        next_state = transitions.get(current_state, {}).get(task["type"])
        if next_state:
            self.candidate_states[candidate_id] = next_state
            next_agent = self._get_next_agent(next_state)
            if next_agent:
                self._schedule_next_task(next_agent, candidate_id, task["job_id"])
```

### 6.3 专业Agent基类

```python
class RecruitmentAgent:
    """招聘专业Agent基类"""

    def __init__(self, agent_type: str, system_prompt: str,
                 context_builder: ContextBuilder,
                 memory_manager: MemoryManager,
                 note_tool: NoteTool):
        self.agent_type = agent_type
        self.system_prompt = system_prompt
        self.context_builder = context_builder
        self.memory_manager = memory_manager
        self.note_tool = note_tool
        self.llm = HelloAgentsLLM()

    def run(self, context: str, task: Dict) -> Dict:
        """执行Agent任务"""
        messages = [
            {"role": "system", "content": context},
            {"role": "user", "content": json.dumps(task, ensure_ascii=False)}
        ]
        response = self.llm.invoke(messages)
        return self._parse_response(response)

    def _parse_response(self, response: str) -> Dict:
        """解析Agent输出为结构化结果"""
        parsers = {
            "sourcing": self._parse_sourcing,
            "screening": self._parse_screening,
            "interview": self._parse_interview,
            "offering": self._parse_offering,
            "onboarding": self._parse_onboarding,
            "analytics": self._parse_analytics
        }
        return parsers.get(self.agent_type, lambda x: {"raw": x})(response)
```

### 6.4 使用示例

```python
def demo():
    """演示完整招聘流程"""

    # 初始化系统
    config = RecruitmentMemoryConfig()
    orchestrator = RecruitmentOrchestrator(config)

    # 步骤1: 寻访Agent
    sourcing_result = orchestrator.process({
        "type": "sourcing",
        "job_id": "J001",
        "instruction": "寻访高级Python工程师,优先内部人才库",
        "target_count": 5
    })

    # 步骤2: 筛选Agent
    screening_result = orchestrator.process({
        "type": "screening",
        "job_id": "J001",
        "candidate_id": "C001",
        "instruction": "筛选张三的简历"
    })

    # 步骤3: 面试Agent
    interview_result = orchestrator.process({
        "type": "interview",
        "job_id": "J001",
        "candidate_id": "C001",
        "instruction": "执行初面,重点考察Python和FastAPI",
        "round": "first"
    })

    # 步骤4: 薪酬Agent
    offering_result = orchestrator.process({
        "type": "offering",
        "job_id": "J001",
        "candidate_id": "C001",
        "instruction": "制定Offer方案,候选人期望35K"
    })

    # 步骤5: 入职Agent
    onboarding_result = orchestrator.process({
        "type": "onboarding",
        "job_id": "J001",
        "candidate_id": "C001",
        "instruction": "准备入职材料,入职日期2026-06-15"
    })

    # 步骤6: 数据Agent
    analytics_result = orchestrator.process({
        "type": "analytics",
        "job_id": "J001",
        "instruction": "分析J001岗位的招聘效能"
    })

    # 查看候选人完整事件链
    episodes = orchestrator.episodic_memory.search(
        query="C001",
        memory_type="episodic"
    )
    print(f"候选人C001共经历 {len(episodes)} 个招聘事件")


if __name__ == "__main__":
    demo()
```

---

## 七、关键设计决策总结

| 设计点 | 决策 | 理由 |
|-------|------|------|
| **记忆分层** | 4层记忆映射招聘场景 | 工作记忆=当前活跃候选人,情景记忆=招聘事件链,语义记忆=人才画像,感知记忆=简历/录音 |
| **上下文定制** | 每Agent独立ContextBuilder配置 | 寻访需要人才地图,面试需要题库,薪酬需要基准数据 |
| **笔记系统** | 两类笔记:岗位项目+候选人档案 | 岗位笔记追踪漏斗,候选人笔记追踪全生命周期 |
| **记忆流转** | Orchestrator协调,EpisodicMemory串联 | 保证6个Agent看到一致的候选人历史 |
| **RAG命名空间** | 5个独立知识库 | JD、面试题、制度、薪酬、法律,避免检索污染 |
| **状态机** | 自动触发下一Agent | new->sourced->screened->interviewing->offered->onboarded |

---

## 八、架构核心优势

1. **每个Agent有独立的上下文策略** - 通过ContextBuilder定制Gather/Select逻辑
2. **统一的记忆系统保持数据一致性** - 4层记忆覆盖全招聘生命周期
3. **NoteTool实现进度可视化** - 岗位漏斗+候选人档案,人类可读可编辑
4. **ContextBuilder确保token效率** - GSSC流水线避免上下文浪费
5. **自动状态流转减少人工干预** - 候选人状态机驱动Agent协作
