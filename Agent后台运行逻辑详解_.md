# Agent 后台运行逻辑详解

> 版本: v1.0 | 日期: 2026-06-01 | 用途: AI招聘Agent后台运行逻辑参考手册

---

## 目录

1. [宏观链路总览](#一宏观链路总览)
2. [第一层: 输入处理层](#二第一层输入处理层)
3. [第二层: 上下文工程层](#三第二层上下文工程层)
4. [第三层: 推理决策层](#四第三层推理决策层)
5. [第四层: 工具执行层](#五第四层工具执行层)
6. [第五层: 结果回传与状态更新](#六第五层结果回传与状态更新)
7. [第六层: 记忆持久化](#七第六层记忆持久化异步)
8. [完整时序图](#八完整时序图)
9. [关键技术组件](#九关键技术组件)
10. [关键设计原则](#十关键设计原则)
11. [状态机伪代码](#十一状态机伪代码)

---

## 一、宏观链路总览

```
用户输入(前端/CLI) -> 输入处理层(预处理) -> 推理决策层(LLM核心) -> 执行输出层(后处理)
```

---

## 二、第一层: 输入处理层

### 2.1 后台执行步骤

| 步骤 | 操作 | 具体说明 |
|------|------|---------|
| 1. 接收输入 | HTTP/WebSocket/CLI 捕获 | 生成唯一 `message_id` |
| 2. 编码转换 | Unicode 标准化 | 处理 emoji、特殊字符、全角半角统一 |
| 3. 敏感词初筛 | 正则匹配 / 本地词库 | 先过滤明显违规内容 |
| 4. 会话关联 | 查 `session_id` | 确定新对话还是已有会话延续 |
| 5. 加载上下文 | 从内存/Redis/DB 读取 | 取出历史消息、当前状态、记忆 |

### 2.2 此时后台内存中的数据结构

```json
{
  "session_id": "sess_abc123",
  "user_id": "qixia",
  "message": {
    "id": "msg_001",
    "content": "帮我寻访Java后端工程师",
    "timestamp": "2026-06-01T16:03:00Z",
    "type": "text"
  },
  "context": {
    "history": [
      {"role": "user", "content": "你好"},
      {"role": "assistant", "content": "您好，我是AI招聘助手..."}
    ],
    "state": {
      "current_intent": null,
      "slots": {},
      "memory_refs": []
    }
  }
}
```

---

## 三、第二层: 上下文工程层

> **最关键的一层，后台在这里"组装"给 LLM 看的"材料包"**

### 3.1 ContextBuilder 后台逻辑

```
1. 系统提示词 (System Prompt)
   -> 从模板库加载，注入当前 Agent 角色、可用工具列表

2. 记忆检索 (Memory Retrieval)
   -> 向量数据库查询: 用户历史偏好、相关岗位、之前的对话摘要
   -> 结果按相似度排序，取 Top-K

3. 对话历史 (Conversation History)
   -> 按时间顺序排列，但受 Token 限制需要裁剪
   -> 策略: 保留最近 N 轮，更早的做摘要压缩

4. 当前状态 (Current State)
   -> 意图、槽位、待办事项、工具执行中间结果

5. 用户最新输入 (User Input)
   -> 经过预处理的原始消息

          |
          V
    组装成最终 Prompt
```

### 3.2 最终 Prompt 结构示例

```markdown
[系统提示词 - 角色定义]
你是AI招聘Agent的Orchestrator，负责理解用户需求并调度子Agent。
可用工具: resume_parser, talent_sourcing, interview_scheduler...
当前时间: 2026-06-01 16:03

[长期记忆 - 用户画像]
用户 qixia 偏好: 关注Java岗、之前找过3个P7级别候选人...

[对话摘要 - 历史压缩]
[摘要] 用户之前询问了Agent功能介绍，未发起具体任务。

[最近对话历史]
user: 你好
assistant: 您好，我是AI招聘助手...
user: 帮我寻访Java后端工程师

[当前状态]
intent: null
slots: {}
pending: []

[指令]
请分析用户意图，判断需要调用什么工具或如何回复。
以JSON格式返回: {"intent": "...", "slots": {...}, "response": "..."}
```

---

## 四、第三层: 推理决策层（LLM Inference）

### 4.1 后台执行步骤

| 步骤 | 后台操作 | 技术细节 |
|------|---------|---------|
| 1. Token 计算 | 统计 Prompt 长度 | 用 tokenizer（如 tiktoken）精确计算 |
| 2. 预算检查 | 确认不超模型上下文窗口 | 如 128K 模型，当前用了 8K，剩余 120K |
| 3. 发送请求 | HTTP POST 到 LLM API | 携带 Prompt + 参数（temperature, max_tokens 等）|
| 4. **流式等待** | SSE/WebSocket 接收增量输出 | 后台维护一个 buffer，逐字累积 |
| 5. 输出解析 | 提取结构化内容 | 如果是 Function Calling，解析 tool_calls |

### 4.2 Function Calling 返回结构

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc",
        "type": "function",
        "function": {
          "name": "talent_sourcing",
          "arguments": "{\"job_title\": "Java后端工程师\", "target_count\": 3}"
        }
      }]
    }
  }]
}
```

**后台解析后:**
- 发现 `tool_calls` 不为空 -> 进入**工具执行分支**
- 提取函数名 `talent_sourcing` 和参数 -> 去工具注册表查找

---

## 五、第四层: 工具执行层

> **Agent 与外部世界交互的核心**

### 5.1 工具执行流程

```
LLM 决定调用 talent_sourcing
           |
           V
+---------------------+
|   工具路由 (Router)  |
|  查注册表: talent_sourcing 对应哪个 MCP Server?
+----------+----------+
           |
           V
+---------------------+
|   参数校验 (Validate) |
|  检查必填参数是否齐全、类型是否正确
+----------+----------+
           |
           V
+---------------------+
|   权限检查 (Auth)    |
|  检查该用户是否有权调用此工具
+----------+----------+
           |
           V
+---------------------+
|   实际执行 (Execute)  |
|  调用 MCP Server / API / 本地函数
|  可能是: HTTP请求、数据库查询、文件读取...
+----------+----------+
           |
           V
+---------------------+
|   结果封装 (Wrap)    |
|  将工具返回的原始数据格式化为 LLM 可理解的文本
+---------------------+
```

### 5.2 招聘Agent寻访工具伪代码

```python
def execute_talent_sourcing(params):
    # 1. 参数校验
    if not params.get("job_title"):
        return {"error": "缺少必填参数 job_title"}
    
    # 2. 调用外部服务（比如接入 Boss直聘 API、内部人才库等）
    result = call_sourcing_api(
        job_title=params["job_title"],
        count=params.get("target_count", 5),
        location=params.get("location")
    )
    
    # 3. 结果处理（可能很长，需要摘要）
    candidates = result["candidates"]  # 可能100条
    
    # 4. 回写给 LLM 的格式（不能太长，否则超 Token）
    return {
        "status": "success",
        "found_count": len(candidates),
        "top_candidates": candidates[:5],  # 只给前5个详细
        "summary": f"共找到 {len(candidates)} 位候选人，..."
    }
```

---

## 六、第五层: 结果回传与状态更新

### 6.1 工具执行后的处理步骤

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1. 结果注入 | 将工具结果加入上下文 | 作为 assistant 的 "function_result" 放入历史 |
| 2. 二次推理 | 再次调用 LLM | 让 LLM 基于工具结果生成最终回复 |
| 3. 状态更新 | 更新 State | 标记槽位已填充、意图已完成等 |
| 4. 记忆写入 | 异步写入向量库 | 将本轮对话向量化，供未来检索 |
| 5. 输出发送 | 返回给用户 | 流式或一次性返回 |

### 6.2 二次推理的 Prompt 结构

```markdown
[系统提示词]（同上）

[对话历史]（包含之前的 + 工具调用 + 工具结果）

[工具执行结果]
talent_sourcing 返回:
- 找到 23 位Java后端工程师
- 前5位: 张三(5年经验)、李四(7年经验)...

[指令]
请基于以上结果，用自然语言向用户汇报，并询问是否需要查看详细简历。
```

---

## 七、第六层: 记忆持久化（异步）

> **用户收到回复后，后台还在做:**

```
+----------------------------------------+
|           异步任务队列 (Queue)          |
+----------------------------------------+
|  1. 对话摘要生成                        |
|     -> 用轻量模型把本轮对话压缩成1-2句话   |
|                                         |
|  2. 向量嵌入 (Embedding)                |
|     -> 用户输入 + Agent回复 -> 向量化      |
|     -> 存入向量数据库（如 Milvus/PGVector）|
|                                         |
|  3. 关键信息提取                        |
|     -> 识别用户偏好、重要事实              |
|     -> 写入结构化记忆表                    |
|                                         |
|  4. 会话状态持久化                      |
|     -> Redis/DB 中更新 session state      |
|     -> 设置过期时间（如30天无活动自动清理） |
+----------------------------------------+
```

---

## 八、完整时序图

```
用户          前端          Agent后台          LLM API         MCP工具        向量库
 |             |               |                |               |              |
 |--"帮我寻访Java"--> |               |                |               |              |
 |             |---HTTP POST----> |                |               |              |
 |             |               |--1.加载上下文----> |               |              |
 |             |               |  (查Redis/DB)    |               |              |
 |             |               |--2.组装Prompt---> |               |              |
 |             |               |                |               |              |
 |             |               |--3.调用LLM-----> |               |              |
 |             |               |<--4.返回意图----|               |              |
 |             |               |  {"intent":"sourcing",           |              |
 |             |               |   "slots":{...}} |               |              |
 |             |               |                |               |              |
 |             |               |--5.槽位检查-----|               |              |
 |             |               |  发现JD缺失      |               |              |
 |             |               |                |               |              |
 |             |               |--6.追问用户<----|               |              |
 |             |<--------------|                |               |              |
 |<--"请提供JD"--|               |                |               |              |
 |             |               |                |               |              |
 |--"JD是..."---> |               |                |               |              |
 |             |---HTTP POST----> |                |               |              |
 |             |               |--7.更新槽位-----|               |              |
 |             |               |--8.再次调用LLM--> |               |              |
 |             |               |                |               |              |
 |             |               |<-9.返回工具调用--|               |              |
 |             |               |  tool_calls     |               |              |
 |             |               |                |               |              |
 |             |               |--10.路由到MCP---|--------------> |              |
 |             |               |                |  执行寻访逻辑   |              |
 |             |               |                |<-11.返回结果---|              |
 |             |               |                |               |              |
 |             |               |--12.结果注入---> |               |              |
 |             |               |  二次推理        |               |              |
 |             |               |<-13.最终回复----|               |              |
 |             |               |                |               |              |
 |             |               |--14.异步写记忆----------------------------------> |
 |             |               |  (向量+摘要)     |               |              |
 |             |               |                |               |              |
 |             |<--------------|                |               |              |
 |<--"找到23人.."|               |                |               |              |
 |             |               |                |               |              |
```

---

## 九、关键技术组件

| 组件 | 作用 | 技术栈对应 |
|------|------|-------------|
| **消息队列** | 异步处理、削峰 | 可选: Redis Stream / RabbitMQ |
| **状态存储** | 会话状态实时读写 | Redis（快）+ PostgreSQL（持久）|
| **向量数据库** | 长期记忆检索 | Milvus / PGVector / Chroma |
| **LLM 网关** | 统一管理多模型调用 | 自己封装 / LiteLLM |
| **MCP 注册中心** | 工具发现与路由 | 你的工具注册表 |
| **日志追踪** | 全链路可观测 | LangSmith / 自建日志 |
| **Token 计数器** | 成本控制 | tiktoken 实时统计 |

---

## 十、关键设计原则

| 原则 | 说明 |
|------|------|
| **无状态设计** | 每次请求都重新加载上下文，便于水平扩展 |
| **快速失败** | 工具调用超时/报错，立即降级，不卡死 |
| **流式响应** | LLM 输出逐字推给用户，减少等待感 |
| **异步写记忆** | 记忆持久化不阻塞主链路 |
| **幂等性** | 同一消息重复发送，结果一致，防重放 |

---

## 十一、状态机伪代码

```python
class AgentStateMachine:
    # Agent 后台运行状态机
    
    def __init__(self):
        self.state = "IDLE"  # 初始状态
        self.slots = {}
        self.context = []
    
    async def process(self, user_input: str) -> str:
        # 主处理流程
        
        # === 第一层: 输入处理 ===
        message = self._preprocess_input(user_input)
        self.context = await self._load_context(message.session_id)
        
        # === 第二层: 上下文组装 ===
        prompt = self._build_prompt(
            system_prompt=self._load_system_prompt(),
            memory=await self._retrieve_memory(message.user_id),
            history=self.context.history,
            state=self.state,
            user_input=message.content
        )
        
        # === 第三层: LLM推理 ===
        llm_response = await self._call_llm(prompt)
        
        # === 分支判断 ===
        if llm_response.has_tool_calls:
            # === 第四层: 工具执行 ===
            tool_results = await self._execute_tools(llm_response.tool_calls)
            
            # 结果注入，二次推理
            prompt_with_results = self._inject_tool_results(prompt, tool_results)
            final_response = await self._call_llm(prompt_with_results)
            
            # 更新状态
            self._update_state(llm_response.intent, llm_response.slots)
        else:
            final_response = llm_response
        
        # === 第五层: 输出 ===
        await self._stream_response(final_response.content)
        
        # === 第六层: 异步持久化 ===
        asyncio.create_task(self._async_persist(
            session_id=message.session_id,
            user_input=message.content,
            agent_response=final_response.content,
            state=self.state
        ))
        
        return final_response.content
    
    async def _execute_tools(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
        # 工具执行流程
        results = []
        for call in tool_calls:
            # 1. 路由
            handler = self.tool_registry.get(call.name)
            
            # 2. 校验
            validated = handler.validate(call.arguments)
            if not validated.ok:
                results.append(ToolResult(error=validated.error))
                continue
            
            # 3. 执行
            try:
                result = await handler.execute(validated.params)
                results.append(ToolResult(data=result))
            except Exception as e:
                results.append(ToolResult(error=str(e)))
        
        return results
    
    async def _async_persist(self, **kwargs):
        # 异步持久化: 摘要 + 向量 + 状态
        # 1. 生成摘要
        summary = await self._generate_summary(
            kwargs["user_input"], 
            kwargs["agent_response"]
        )
        
        # 2. 向量嵌入
        embedding = await self._embed_text(summary)
        await self.vector_db.upsert(
            id=kwargs["session_id"],
            vector=embedding,
            metadata={"summary": summary, "timestamp": now()}
        )
        
        # 3. 状态持久化
        await self.state_store.save(
            session_id=kwargs["session_id"],
            state=kwargs["state"]
        )
```

---

## 附录: 快速查阅表

### A. 六层对应关系

| 层级 | 名称 | 核心职责 | 是否阻塞主链路 |
|------|------|---------|-------------|
| 1 | 输入处理 | 接收、编码、加载上下文 | 是 |
| 2 | 上下文工程 | 组装 Prompt | 是 |
| 3 | 推理决策 | LLM 调用、意图识别 | 是 |
| 4 | 工具执行 | MCP 工具路由与执行 | 是 |
| 5 | 结果回传 | 二次推理、状态更新、输出 | 是 |
| 6 | 记忆持久化 | 摘要、向量、持久化 | 否（异步）|

### B. 关键数据流转

```
用户输入 -> message_id/session_id -> 加载 context -> 组装 Prompt 
  -> LLM 返回 intent/slots/tool_calls -> 槽位检查
    -> 缺失: 追问用户（回到输入层）
    -> 完整: 执行工具 -> 工具结果 -> 二次 LLM 调用 -> 最终回复 -> 异步写记忆
```

---

> 使用建议: 每次开发新功能或调试时，对照此文档检查数据在哪一层、状态在哪个阶段，能快速定位问题。
