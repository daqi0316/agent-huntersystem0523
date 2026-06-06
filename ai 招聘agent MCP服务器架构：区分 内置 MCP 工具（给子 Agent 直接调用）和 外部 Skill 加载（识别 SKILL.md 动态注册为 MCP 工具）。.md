![[Pasted image 20260606153602.png]]


## 双轨架构核心设计

### 设计原则
| 原则                  | 说明                          |
| ------------------- | --------------------------- |
| **A轨道：内置 MCP 工具**   | 覆盖招聘核心闭环，随系统部署，子 Agent 直接调用 |
| **B轨道：外部 Skill 加载** | 扩展通用能力，运行时动态加载，社区共享         |
| **统一协议层**           | 两者都通过 MCP 协议层调度，对上层透明       |
| **隔离与解耦**           | 内置工具与主系统同进程，Skill 独立运行      |

### A轨道 vs B轨道 对比
| 对比维度     | A轨道：内置 MCP 工具                            | B轨道：外部 Skill 加载                          |
| -------- | ---------------------------------------- | ---------------------------------------- |
| **部署方式** | 随主系统部署                                   | 运行时动态加载                                  |
| **加载时机** | 系统启动时                                    | 按需/定时扫描                                  |
| **调用对象** | 子 Agent 直接调用                             | 任何 Agent 均可调用                            |
| **工具数量** | 37个（固定）                                  | 无限扩展                                     |
| **来源**   | 系统内置                                     | 本地文件/远程URL/社区                            |
| **更新方式** | 系统升级                                     | 热插拔，无需重启                                 |
| **隔离性**  | 与主系统同进程                                  | 独立进程/容器                                  |
| **故障影响** | 影响主系统                                    | 隔离，不影响主系统                                |
| **适用场景** | 招聘核心业务                                   | 通用能力、第三方服务                               |
| **典型示例** | `create_candidate`, `schedule_interview` | `weather`, `web_search`, `tavily_search` |

### A轨道：内置 MCP 工具（37个 → 10个 Server）

**给子 Agent 直接调用**，覆盖招聘全流程：
MCP-Candidate (8个工具)     → 候选人CRUD、搜索、画像
MCP-Job (5个工具)            → 职位CRUD、JD生成
MCP-Application (3个工具)    → 申请记录、状态流转、初筛
MCP-Interview (7个工具)      → 面试排期、取消、改期、完成
MCP-Evaluation (4个工具)     → 评分、报告、反馈
MCP-Resume (2个工具)         → 单份/批量简历解析
MCP-Utils (4个工具)          → 计算、问候、时间、日志
MCP-Dashboard (1个工具)      → 招聘统计数据
MCP-Knowledge (2个工具)      → 知识库搜索、问答
MCP-Search (1个工具)         → tavily深度搜索

### B轨道：外部 Skill 加载（SKILL.md → 动态 MCP 工具）

**识别 `SKILL.md` 文件，动态注册为可调用的 MCP 工具**：

#### Skill 加载流程
① Skill 发现 (Discovery)
   → 扫描目录 ./skills/ 或远程URL
   → 识别所有 SKILL.md 文件

② Skill 解析 (Parser)
   → 读取 SKILL.md 元数据
   → 提取: name / description / version / parameters / handler

③ Skill 注册 (Registry)
   → 转换为 MCP Tool Schema
   → 注册到工具注册表 (Tool Registry)

④ 加载 (Load)
   → 动态挂载到 MCP Host
   → 即时可用，无需重启

#### SKILL.md 文件格式示例
---
name: web_search
description: 互联网实时搜索，获取新闻、知识、数据等最新信息
version: 1.0.0
author: community
tags: [search, internet, news]
---

## Parameters
- query: string (required) - 搜索关键词
- max_results: integer (optional) - 最大结果数，默认5
- time_range: string (optional) - 时间范围: day/week/month/year

## Handler
```python
def run(params):
    import requests
    response = requests.get(
        "https://api.search.com/search",
        params={
            "q": params["query"], 
            "limit": params.get("max_results", 5),
            "time_range": params.get("time_range", "week")
        }
    )
    return {
        "results": response.json().get("results", []),
        "total": response.json().get("total", 0)
    }
    
```  
## Examples

- Input: {"query": "AI招聘最新趋势", "max_results": 3}
    
- Output: {"results": [...], "total": 156}
    

## Error Handling

- 网络超时: 返回 {"error": "timeout", "message": "搜索服务超时"}
    
- API限制: 返回 {"error": "rate_limit", "message": "请求频率超限"}

#### 当前已加载的 Skill 示例

| Skill 名称 | 来源 | 功能 | 状态 |
|-----------|------|------|------|
| `weather` | 官方 Skill 库 | 全球城市实时天气 | ✅ 已加载 |
| `web_search` | 官方 Skill 库 | 互联网实时搜索 | ✅ 已加载 |
| `tavily_search` | 第三方 Skill | AI 增强深度搜索 | ✅ 已加载 |
| `github_search` | 社区贡献 | GitHub 仓库搜索 | ✅ 已加载 |

---

### 统一调用流程

无论是 A轨道 还是 B轨道，调用流程完全一致：
用户提问 → 意图识别 → 任务规划 → 大模型 Function Calling ↓ MCP 协议层 (统一调度) ↓ ┌───────────────┴───────────────┐ ↓ ↓ A轨道: 内置工具 B轨道: Skill (MCP-Interview) (weather) ↓ ↓ 执行 schedule_interview() 执行 weather.run() ↓ ↓ 返回结果 → 大模型整理 → 用户收到回答


---

### 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 为什么内置工具不也用 Skill？ | 核心业务需要稳定性 | 招聘核心流程不能依赖外部文件 |
| 为什么 Skill 也要走 MCP 协议？ | 统一接口，降低复杂度 | 上层无需区分内置/外部 |
| Skill 如何隔离？ | 独立进程/容器 | 防止 Skill 故障影响主系统 |
| Skill 如何更新？ | 热插拔 + 版本管理 | 支持 A/B 测试和回滚 |
| 如何发现新 Skill？ | 定时扫描 + 手动触发 | 灵活可控 |

---


---

### 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 为什么内置工具不也用 Skill？ | 核心业务需要稳定性 | 招聘核心流程不能依赖外部文件 |
| 为什么 Skill 也要走 MCP 协议？ | 统一接口，降低复杂度 | 上层无需区分内置/外部 |
| Skill 如何隔离？ | 独立进程/容器 | 防止 Skill 故障影响主系统 |
| Skill 如何更新？ | 热插拔 + 版本管理 | 支持 A/B 测试和回滚 |
| 如何发现新 Skill？ | 定时扫描 + 手动触发 | 灵活可控 |

---

下载高清图：

[招聘 Agent 双轨工具架构图](sandbox:///mnt/agents/output/recruitment_agent_dual_track_architecture.png)

需要我把这份设计写成 **完整的 Markdown 技术文档**（包含每个 Skill 的接口定义、加载器代码示例、错误处理策略），或者针对 **Skill 加载器的具体实现**（Python 代码）详细展开吗？

## 一、内部 MCP 工具（Built-in Tools）

### 1.1 设计目标
| 目标      | 说明                        |
| ------- | ------------------------- |
| **稳定性** | 招聘核心流程必须 100% 可用，不能依赖外部文件 |
| **性能**  | 子 Agent 频繁调用，需要低延迟        |
| **一致性** | 所有子 Agent 使用同一套工具，行为一致    |
| **可维护** | 代码在版本控制中，可追踪、可回滚          |

### 1.2 架构位置
┌─────────────────────────────────────────┐
│           编排层 Orchestrator             │
│    ┌─────────┐    ┌─────────┐           │
│    │ 简历解析 Agent │    │ 寻访 Agent    │           │
│    └────┬────┘    └────┬────┘           │
│         │              │                  │
│    ┌────┴──────────────┴────┐            │
│    │   MCP Client (内置)     │            │
│    │   • 本地连接 (stdio)     │            │
│    │   • 零网络开销          │            │
│    └────┬──────────────┬────┘            │
│         │              │                  │
│    ┌────┴────┐    ┌────┴────┐             │
│    │MCP-Candidate│    │MCP-Interview│     │
│    │  进程内    │    │  进程内    │     │
│    └─────────┘    └─────────┘            │
└─────────────────────────────────────────┘

### 1.3 10个内置 MCP Server 详细定义

#### Server 1: MCP-Candidate（候选人管理）

**工具清单（8个）**:
| 工具名                        | 方法                             | 输入                                   | 输出                       |
| -------------------------- | ------------------------------ | ------------------------------------ | ------------------------ |
| `create_candidate`         | `POST /candidates`             | `{name, email, phone, source}`       | `{candidate_id, status}` |
| `update_candidate`         | `PUT /candidates/{id}`         | `{candidate_id, name?, email?, ...}` | `{updated_fields}`       |
| `archive_candidate`        | `DELETE /candidates/{id}`      | `{candidate_id, reason?}`            | `{status: archived}`     |
| `get_candidate`            | `GET /candidates/{id}`         | `{candidate_id}`                     | 完整候选人信息                  |
| `get_candidate_detail`     | `GET /candidates/{id}/detail`  | `{candidate_id}`                     | 含面试/申请记录                 |
| `get_candidate_profile`    | `GET /candidates/{id}/profile` | `{candidate_id}`                     | 聚合画像                     |
| `search_candidates`        | `GET /candidates`              | `{keywords?, status?, page?}`        | 分页列表                     |
| `search_candidates_filter` | `GET /candidates/filter`       | `{skills?, experience?, ...}`        | 筛选结果                     |


**JSON-RPC 接口定义**:
{
  "name": "create_candidate",
  "description": "创建新候选人档案。当用户提供候选人基本信息时调用。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "候选人姓名"},
      "email": {"type": "string", "format": "email", "description": "邮箱"},
      "phone": {"type": "string", "pattern": "^1[3-9]\\d{9}$", "description": "手机号"},
      "source": {"type": "string", "enum": ["boss", "liepin", "referral", "website"]}
    },
    "required": ["name", "email"]
  }
}

**调用示例**:
# 子 Agent 内部调用
result = await mcp_client.call(
    server="MCP-Candidate",
    tool="create_candidate",
    arguments={
        "name": "张三",
        "email": "zhangsan@example.com",
        "phone": "13800138000",
        "source": "boss"
    }
)
# 返回: {"candidate_id": "cand_12345", "status": "active"}

#### Server 2: MCP-Job（职位管理）

**工具清单（5个）**:
| 工具名           | 功能       | 关键参数                                    |
| ------------- | -------- | --------------------------------------- |
| `generate_jd` | AI生成职位描述 | `job_title`, `required_skills`, `level` |
| `create_job`  | 创建职位     | `title`, `department`, `location`       |
| `update_job`  | 更新职位     | `job_id`, `description?`, `status?`     |
| `close_job`   | 关闭职位     | `job_id`, `reason`                      |
| `list_jobs`   | 职位列表     | `status?`, `department?`, `page?`       |

#### Server 3: MCP-Application（申请流程）

**工具清单（3个）**:
| 工具名                         | 功能   | 状态流转                                |
| --------------------------- | ---- | ----------------------------------- |
| `create_application`        | 创建申请 | `screening` →                       |
| `update_application_status` | 更新状态 | → `passed` / `failed` / `interview` |
| `screen_resume`             | AI初筛 | 返回匹配度评分                             |

#### Server 4: MCP-Interview（面试管理）

**工具清单（7个）**:
| 工具名                       | 功能   | 注意事项       |
| ------------------------- | ---- | ---------- |
| `schedule_interview`      | 安排面试 | 检查时间冲突     |
| `cancel_interview`        | 取消面试 | 通知候选人      |
| `reschedule_interview`    | 改期   | 新时间冲突检测    |
| `complete_interview`      | 标记完成 | 关联评估记录     |
| `get_interview_detail`    | 面试详情 | 含候选人/职位/反馈 |
| `get_upcoming_interviews` | 未来面试 | 按天数查询      |
| `get_schedule`            | 日程查询 | 按月统计       |

**时间冲突检测逻辑**:
async def schedule_interview(arguments):
    candidate_id = arguments["candidate_id"]
    scheduled_at = arguments["scheduled_at"]
    
    # 1. 检查候选人是否有其他面试
    existing = await db.query(
        "SELECT * FROM interviews WHERE candidate_id = ? AND status = 'scheduled' AND scheduled_at = ?",
        candidate_id, scheduled_at
    )
    if existing:
        return {"error": "候选人该时间已有其他面试安排"}
    
    # 2. 检查面试官是否可用
    for interviewer in arguments["interviewers"]:
        busy = await check_interviewer_availability(interviewer, scheduled_at)
        if busy:
            return {"error": f"面试官 {interviewer} 该时间不可用"}
    
    # 3. 创建面试记录
    interview_id = await db.insert("interviews", {
        "candidate_id": candidate_id,
        "job_id": arguments["job_id"],
        "scheduled_at": scheduled_at,
        "interviewers": json.dumps(arguments["interviewers"]),
        "status": "scheduled"
    })
    
    # 4. 更新申请状态
    await update_application_status(arguments["application_id"], "interview")
    
    return {"interview_id": interview_id, "status": "scheduled"}

#### Server 5-10: 其他内置 Server
| Server             | 工具数 | 核心功能                                                                                  |
| ------------------ | --- | ------------------------------------------------------------------------------------- |
| **MCP-Evaluation** | 4   | `save_evaluation`, `generate_evaluation_report`, `record_feedback`, `get_evaluations` |
| **MCP-Resume**     | 2   | `parse_resume` (PDF/DOC解析), `batch_parse_resumes`                                     |
| **MCP-Utils**      | 4   | `calculate`, `greet`, `get_current_time`, `log_operation`                             |
| **MCP-Dashboard**  | 1   | `get_dashboard_stats` (招聘漏斗统计)                                                        |
| **MCP-Knowledge**  | 2   | `search_documents`, `search_knowledge`                                                |
| **MCP-Search**     | 1   | `tavily_search` (深度搜索)                                                                |

### 1.4 内置 MCP Server 启动流程
# mcp_server_builtin.py
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server_transport

class BuiltInMCPServer:
    def __init__(self, name, tools):
        self.name = name
        self.tools = tools  # 工具字典
        self.server = Server(name)
        
    def register_tools(self):
        """注册所有工具到 MCP Server"""
        for tool_name, tool_def in self.tools.items():
            self.server.register_tool(
                name=tool_name,
                description=tool_def["description"],
                input_schema=tool_def["input_schema"],
                handler=tool_def["handler"]
            )
    
    async def run(self):
        """启动 Server，通过 stdio 与 MCP Host 通信"""
        self.register_tools()
        async with stdio_server_transport() as transport:
            await self.server.run(transport)

# 启动示例
async def main():
    # 定义 MCP-Candidate 的所有工具
    candidate_tools = {
        "create_candidate": {
            "description": "创建候选人...",
            "input_schema": {...},
            "handler": create_candidate_handler
        },
        # ... 其他7个工具
    }
    
    server = BuiltInMCPServer("MCP-Candidate", candidate_tools)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())

### 1.5 内置工具调用时序图
用户: "帮我安排张三明天下午3点面试"
  │
  ▼
┌─────────────────┐
│  意图识别        │ → "schedule_interview"
│  Intent         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  槽位管理        │ → 收集: candidate_id="cand_123", time="明天15:00"
│  Slot Filling   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  大模型 Function │ → 生成调用指令
│  Calling        │
│                 │
│  {              │
│    "tool": "MCP-Interview/schedule_interview",
│    "arguments": {candidate_id, job_id, time, interviewers}
│  }              │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  MCP Host       │ → 路由到 MCP-Interview Server
│  (内置)         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  MCP-Interview  │ → 执行 schedule_interview()
│  Server         │   1. 检查冲突
│  (进程内)        │   2. 创建记录
│                 │   3. 更新状态
│                 │   4. 记录日志
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  返回结果        │ → {interview_id: "int_001", status: "scheduled"}
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  大模型整理      │ → "已安排张三明天15:00面试，面试官：王总监"
│  最终回答        │
└─────────────────┘

## 二、外部 Skill 加载（Dynamic Skills）

### 2.1 设计目标
| 目标      | 说明                     |
| ------- | ---------------------- |
| **扩展性** | 不修改主代码就能增加新能力          |
| **社区化** | 复用他人 Skill，共享自己的 Skill |
| **隔离性** | Skill 故障不影响主系统         |
| **热插拔** | 不停机加载、更新、卸载            |

### 2.2 架构位置
┌─────────────────────────────────────────┐
│           编排层 Orchestrator             │
│              │                          │
│    ┌────────┴────────┐                 │
│    │   MCP Host       │                 │
│    │   (统一调度)      │                 │
│    └────────┬────────┘                 │
│              │                          │
│    ┌─────────┴──────────┐              │
│    │                    │              │
│    ▼                    ▼              │
│ ┌─────────┐      ┌──────────────┐      │
│ │ 内置工具  │      │  Skill Loader  │      │
│ │ (进程内)  │      │  (独立进程)    │      │
│ └─────────┘      └──────┬───────┘      │
│                         │              │
│              ┌──────────┼──────────┐   │
│              ▼          ▼          ▼   │
│         ┌────────┐ ┌────────┐ ┌────────┐│
│         │weather │ │web_search│ │github  ││
│         │ Skill  │ │ Skill  │ │ Skill  ││
│         │(Python)│ │(Python)│ │(JS)    ││
│         └────────┘ └────────┘ └────────┘│
│                                         │
│    Skill 来源:                          │
│    • ./skills/weather/SKILL.md          │
│    • https://github.com/.../SKILL.md    │
│    • 远程 URL                           │
└─────────────────────────────────────────┘

### 2.3 SKILL.md 文件格式规范

#### 2.3.1 完整格式定义
---
# 元数据头部 (YAML Front Matter)
name: web_search                    # 工具名（唯一标识）
description: 互联网实时搜索          # 描述（给大模型看）
version: 1.0.0                      # 版本号
author: qixia                       # 作者
tags: [search, internet, news]      # 标签（分类用）
icon: 🔍                           # 图标（可选）
requires:                           # 依赖（可选）
  - python-requests
  - python-dotenv
env:                                # 环境变量（可选）
  - SEARCH_API_KEY: 搜索API密钥
---

## Parameters
# 参数定义（MCP Schema 格式）

- query: 
    type: string
    required: true
    description: 搜索关键词
    examples: ["AI招聘趋势", "Java面试题"]

- max_results:
    type: integer
    required: false
    default: 5
    description: 最大结果数
    minimum: 1
    maximum: 20

- time_range:
    type: string
    required: false
    default: "week"
    enum: [day, week, month, year]
    description: 时间范围

## Handler
# 执行逻辑（支持多语言）

```python
import os
import requests

def run(params: dict) -&gt; dict:
    """
    Skill 执行入口函数
    params: 用户传入的参数
    return: 必须返回 dict，会被序列化为 JSON
    """
    api_key = os.getenv("SEARCH_API_KEY")
    
    try:
        response = requests.get(
            "https://api.search.com/v1/search",
            headers={"Authorization": f"Bearer {api_key}"},
            params={
                "q": params["query"],
                "limit": params.get("max_results", 5),
                "time_range": params.get("time_range", "week")
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            "success": True,
            "results": data.get("results", []),
            "total": data.get("total", 0),
            "query": params["query"]
        }
        
    except requests.Timeout:
        return {
            "success": False,
            "error": "timeout",
            "message": "搜索服务超时，请稍后重试"
        }
    except requests.HTTPError as e:
        return {
            "success": False,
            "error": "api_error",
            "message": f"API错误: {e.response.status_code}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "unknown",
            "message": str(e)
        }
        
        
```
## Examples

# 示例（帮助大模型理解如何使用）

### 示例1: 搜索新闻

- Input:
{"query": "AI招聘最新趋势", "max_results": 3}
Output:
{
  "success": true,
  "results": [
    {"title": "2026年AI招聘市场报告", "url": "...", "snippet": "..."}
  ],
  "total": 156
}

### 示例2: 搜索技术文档

- Input:
    
    JSON
    
    ```json
    {"query": "Spring Boot 3.0 新特性", "time_range": "month"}
    ```
    
- Output:
    
    JSON
    
    ```json
    {"success": true, "results": [...], "total": 42}
    ```

## Error Handling

# 错误处理说明
| 错误码             | 场景    | 处理方式     |
| --------------- | ----- | -------- |
| timeout         | 网络超时  | 提示用户重试   |
| rate\_limit     | 频率限制  | 等待后重试    |
| api\_error      | API错误 | 检查API密钥  |
| invalid\_params | 参数错误  | 返回参数校验信息 |

## Tests

# 测试用例（可选，用于验证）
def test_basic_search():
    result = run({"query": "Python", "max_results": 1})
    assert result["success"] is True
    assert len(result["results"]) == 1

def test_empty_query():
    result = run({"query": ""})
    assert result["success"] is False
    assert result["error"] == "invalid_params"


---

### 2.4 Skill 加载器实现

#### 2.4.1 核心加载器代码

```python
# skill_loader.py
import os
import re
import yaml
import json
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class SkillDefinition:
    """Skill 定义数据结构"""
    name: str
    description: str
    version: str
    author: str
    tags: List[str]
    parameters: Dict  # MCP Schema 格式
    handler_code: str  # 执行代码
    handler_language: str  # python / javascript / shell
    examples: List[Dict]
    error_handling: Dict
    env_vars: List[str]  # 需要的环境变量
    source_path: str  # 来源路径
    
class SkillLoader:
    """Skill 加载器：发现 → 解析 → 注册 → 加载"""
    
    def __init__(self, registry, mcp_host):
        self.registry = registry  # 工具注册表
        self.mcp_host = mcp_host  # MCP Host
        self.loaded_skills: Dict[str, SkillDefinition] = {}
        self.skill_dir = "./skills"
        self.remote_sources = []  # 远程源列表
        
    async def discover(self) -> List[str]:
        """
        ① Skill 发现：扫描所有 SKILL.md 文件
        """
        skill_paths = []
        
        # 1. 扫描本地目录
        if os.path.exists(self.skill_dir):
            for root, dirs, files in os.walk(self.skill_dir):
                for file in files:
                    if file == "SKILL.md":
                        skill_paths.append(os.path.join(root, file))
        
        # 2. 扫描远程源（如果配置了）
        for remote_url in self.remote_sources:
            remote_skills = await self._fetch_remote_skills(remote_url)
            skill_paths.extend(remote_skills)
        
        return skill_paths
    
    async def parse(self, skill_path: str) -> SkillDefinition:
        """
        ② Skill 解析：读取 SKILL.md 提取元数据和代码
        """
        with open(skill_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 1. 解析 YAML Front Matter
        front_matter_match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
        if not front_matter_match:
            raise ValueError(f"SKILL.md 缺少 YAML Front Matter: {skill_path}")
        
        metadata = yaml.safe_load(front_matter_match.group(1))
        
        # 2. 提取各部分内容
        sections = self._parse_sections(content[front_matter_match.end():])
        
        # 3. 解析参数定义
        parameters = self._parse_parameters(sections.get("Parameters", ""))
        
        # 4. 提取 Handler 代码
        handler_code, handler_language = self._extract_handler(sections.get("Handler", ""))
        
        # 5. 提取示例
        examples = self._parse_examples(sections.get("Examples", ""))
        
        # 6. 提取错误处理
        error_handling = self._parse_error_handling(sections.get("Error Handling", ""))
        
        return SkillDefinition(
            name=metadata["name"],
            description=metadata["description"],
            version=metadata.get("version", "1.0.0"),
            author=metadata.get("author", "unknown"),
            tags=metadata.get("tags", []),
            parameters=parameters,
            handler_code=handler_code,
            handler_language=handler_language,
            examples=examples,
            error_handling=error_handling,
            env_vars=metadata.get("env", []),
            source_path=skill_path
        )
    
    def _parse_sections(self, content: str) -> Dict[str, str]:
        """按 ## 标题分割各部分内容"""
        sections = {}
        current_section = None
        current_content = []
        
        for line in content.split('\n'):
            if line.startswith('## '):
                if current_section:
                    sections[current_section] = '\n'.join(current_content)
                current_section = line[3:].strip()
                current_content = []
            else:
                current_content.append(line)
        
        if current_section:
            sections[current_section] = '\n'.join(current_content)
        
        return sections
    
    def _parse_parameters(self, param_text: str) -> Dict:
        """解析参数定义，转换为 MCP Schema"""
        # 简化实现，实际可用 yaml 解析
        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # 解析 - name: type (required) - description 格式
        for line in param_text.split('\n'):
            match = re.match(r'-\s+(\w+):\s+(\w+)\s+\((\w+)\)\s+-\s+(.*)', line.strip())
            if match:
                name, ptype, required, desc = match.groups()
                schema["properties"][name] = {
                    "type": ptype,
                    "description": desc
                }
                if required == "required":
                    schema["required"].append(name)
        
        return schema
    
    def _extract_handler(self, handler_text: str) -> tuple:
        """提取 Handler 代码块和语言"""
        # 查找 ```python / ```javascript 代码块
        code_match = re.search(r'```(\w+)\n(.*?)```', handler_text, re.DOTALL)
        if code_match:
            language = code_match.group(1)
            code = code_match.group(2)
            return code, language
        
        raise ValueError("Handler 代码块格式错误")
    
    def _parse_examples(self, examples_text: str) -> List[Dict]:
        """解析示例"""
        examples = []
        # 简化实现
        return examples
    
    def _parse_error_handling(self, error_text: str) -> Dict:
        """解析错误处理定义"""
        # 简化实现
        return {}
    
    async def register(self, skill: SkillDefinition):
        """
        ③ Skill 注册：转换为 MCP Tool 并注册到注册表
        """
        # 1. 生成 MCP Tool Schema
        tool_schema = {
            "name": skill.name,
            "description": skill.description,
            "inputSchema": skill.parameters
        }
        
        # 2. 创建执行包装器
        async def skill_handler(arguments: dict) -> dict:
            """包装 Skill 执行，提供隔离和错误处理"""
            return await self._execute_skill(skill, arguments)
        
        # 3. 注册到工具注册表
        self.registry.register(
            name=skill.name,
            schema=tool_schema,
            handler=skill_handler,
            source="skill",
            skill_def=skill
        )
        
        # 4. 缓存到 MCP Host
        self.mcp_host.cache_tool_schema(skill.name, tool_schema)
        
        self.loaded_skills[skill.name] = skill
        print(f"✅ Skill 注册成功: {skill.name} v{skill.version}")
    
    async def _execute_skill(self, skill: SkillDefinition, arguments: dict) -> dict:
        """
        执行 Skill，提供隔离和错误处理
        """
        # 1. 检查环境变量
        for env_var in skill.env_vars:
            if not os.getenv(env_var):
                return {
                    "success": False,
                    "error": "missing_env",
                    "message": f"缺少环境变量: {env_var}"
                }
        
        # 2. 参数校验
        validation = self._validate_params(arguments, skill.parameters)
        if not validation["valid"]:
            return {
                "success": False,
                "error": "invalid_params",
                "message": validation["errors"]
            }
        
        # 3. 执行 Skill（根据语言选择执行方式）
        try:
            if skill.handler_language == "python":
                result = await self._execute_python_skill(skill, arguments)
            elif skill.handler_language == "javascript":
                result = await self._execute_javascript_skill(skill, arguments)
            else:
                result = await self._execute_shell_skill(skill, arguments)
            
            # 4. 包装结果
            if isinstance(result, dict):
                return result
            else:
                return {"success": True, "result": result}
                
        except Exception as e:
            return {
                "success": False,
                "error": "execution_error",
                "message": str(e)
            }
    
    async def _execute_python_skill(self, skill: SkillDefinition, arguments: dict) -> dict:
        """执行 Python Skill（在子进程中隔离运行）"""
        import subprocess
        import tempfile
        
        # 创建临时文件存放代码
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # 写入执行代码
            f.write(skill.handler_code)
            f.write(f"\n\nimport json\n")
            f.write(f"result = run({json.dumps(arguments)})\n")
            f.write(f"print(json.dumps(result, ensure_ascii=False))\n")
            temp_path = f.name
        
        try:
            # 在子进程中执行（隔离）
            proc = await asyncio.create_subprocess_exec(
                'python', temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ}  # 传递环境变量
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            
            if proc.returncode != 0:
                return {
                    "success": False,
                    "error": "skill_execution_failed",
                    "message": stderr.decode()
                }
            
            return json.loads(stdout.decode())
            
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "success": False,
                "error": "timeout",
                "message": "Skill 执行超时（30秒）"
            }
        finally:
            os.unlink(temp_path)
    
    async def load(self, skill_name: str = None):
        """
        ④ 加载：主入口，执行完整流程
        """
        # 1. 发现
        skill_paths = await self.discover()
        print(f"🔍 发现 {len(skill_paths)} 个 Skill")
        
        # 2. 解析 & 注册
        for path in skill_paths:
            try:
                skill = await self.parse(path)
                
                # 如果指定了名称，只加载该 Skill
                if skill_name and skill.name != skill_name:
                    continue
                
                # 检查版本（如果已存在）
                if skill.name in self.loaded_skills:
                    existing = self.loaded_skills[skill.name]
                    if existing.version == skill.version:
                        print(f"⏭️  Skill 已加载，跳过: {skill.name}")
                        continue
                    print(f"🔄 更新 Skill: {skill.name} {existing.version} → {skill.version}")
                
                await self.register(skill)
                
            except Exception as e:
                print(f"❌ Skill 加载失败: {path}, 错误: {e}")
                continue
        
        print(f"✅ 加载完成，共 {len(self.loaded_skills)} 个 Skill")
    
    async def unload(self, skill_name: str):
        """卸载 Skill"""
        if skill_name in self.loaded_skills:
            self.registry.unregister(skill_name)
            del self.loaded_skills[skill_name]
            self.mcp_host.remove_tool_schema(skill_name)
            print(f"🗑️  Skill 已卸载: {skill_name}")
    
    async def reload(self, skill_name: str):
        """重新加载 Skill（热更新）"""
        await self.unload(skill_name)
        await self.load(skill_name)
        print(f"🔄 Skill 已重载: {skill_name}")
        
```

### 2.5 Skill 与内置工具的调用对比
| 对比项      | 内置工具                                                            | Skill                                               |
| -------- | --------------------------------------------------------------- | --------------------------------------------------- |
| **调用方式** | `mcp_client.call("MCP-Interview", "schedule_interview", {...})` | `mcp_client.call("weather", "run", {"city": "北京"})` |
| **路由方式** | 通过 Server 名路由                                                   | 通过 Skill 名直接路由                                      |
| **执行环境** | 主进程内                                                            | 子进程隔离                                               |
| **超时控制** | 依赖 Server 配置                                                    | 强制 30 秒超时                                           |
| **错误处理** | Server 统一处理                                                     | Skill 自定义 + 加载器兜底                                   |
| **返回值**  | 直接返回                                                            | 必须包含 `success` 字段                                   |
| **日志记录** | 自动记录到审计日志                                                       | 需显式调用 `log_operation`                               |

### 2.6 Skill 调用时序图
用户: "今天北京天气怎么样？"
  │
  ▼
┌─────────────────┐
│  意图识别        │ → "查询天气" → 需要 weather Skill
│  Intent         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  大模型 Function │ → 生成调用指令
│  Calling        │
│                 │
│  {              │
│    "tool": "weather",    ← 直接调用 Skill 名
│    "arguments": {"city": "北京"}
│  }              │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  MCP Host       │ → 查询工具注册表
│                 │   发现 weather 是 Skill
│                 │   路由到 Skill Loader
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Skill Loader   │ → 查找已加载的 weather Skill
│                 │   获取 handler_code
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  子进程隔离执行   │ → 启动 Python 子进程
│  (30秒超时)      │   执行 weather.run({"city": "北京"})
│                 │   捕获 stdout 作为结果
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  返回结果        │ → {"success": true, "temperature": 28, "weather": "晴"}
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  大模型整理      │ → "北京今天天气晴，气温28°C，适合面试出行！"
│  最终回答        │
└─────────────────┘

### 2.7 Skill 管理命令（CLI）
# 列出所有已加载的 Skill
$ agent skill list

NAME         VERSION   SOURCE                    STATUS
weather      1.0.0     ./skills/weather/        ✅ active
web_search   1.2.0     https://.../web_search   ✅ active
tavily_search 2.0.1    ./skills/tavily/         ✅ active
github_search 0.5.0    ./skills/github/         ⚠️  outdated

# 加载新 Skill
$ agent skill load ./skills/new_skill/
✅ Skill 加载成功: new_skill v1.0.0

# 从远程加载
$ agent skill load https://github.com/.../weather_skill/SKILL.md
✅ Skill 加载成功: weather v1.1.0

# 卸载 Skill
$ agent skill unload github_search
🗑️  Skill 已卸载: github_search

# 更新 Skill
$ agent skill update web_search
🔄 正在检查更新...
✅ web_search 1.2.0 → 1.3.0 更新成功

# 重载所有 Skill
$ agent skill reload-all
🔄 重载 3 个 Skill...
✅ 全部重载完成

# 查看 Skill 详情
$ agent skill info weather

名称: weather
版本: 1.0.0
作者: qixia
描述: 全球城市实时天气查询
来源: ./skills/weather/SKILL.md
状态: ✅ active
调用次数: 156
最后调用: 2026-06-06 14:30

## 三、统一 MCP 协议层

### 3.1 协议层职责

无论内置工具还是 Skill，都通过统一的 MCP 协议层调度：
# mcp_host.py
class MCPHost:
    """MCP Host：统一调度中心"""
    
    def __init__(self):
        self.builtin_servers = {}  # 内置 Server 连接
        self.skill_loader = None   # Skill 加载器
        self.tool_registry = {}      # 统一工具注册表
        self.schema_cache = {}       # 工具描述缓存
        
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        统一调用入口：不区分内置/Skill
        """
        # 1. 检查缓存的工具描述
        if tool_name not in self.schema_cache:
            raise ToolNotFoundError(f"工具不存在: {tool_name}")
        
        # 2. 查询注册表，确定来源
        tool_info = self.tool_registry.get(tool_name)
        
        if not tool_info:
            raise ToolNotFoundError(f"工具未注册: {tool_name}")
        
        # 3. 根据来源路由
        if tool_info["source"] == "builtin":
            # 内置工具：通过 Server 调用
            server_name = tool_info["server"]
            return await self._call_builtin(server_name, tool_name, arguments)
        
        elif tool_info["source"] == "skill":
            # Skill：通过 Skill Loader 调用
            skill_def = tool_info["skill_def"]
            return await self.skill_loader._execute_skill(skill_def, arguments)
        
        else:
            raise ToolError(f"未知工具来源: {tool_info['source']}")
    
    async def _call_builtin(self, server_name: str, tool_name: str, arguments: dict) -> dict:
        """调用内置工具"""
        server = self.builtin_servers.get(server_name)
        if not server:
            raise ServerNotFoundError(f"Server 未连接: {server_name}")
        
        return await server.call_tool(tool_name, arguments)
    
    def register_builtin(self, server_name: str, tools: list):
        """注册内置 Server 的工具"""
        for tool in tools:
            self.tool_registry[tool["name"]] = {
                "source": "builtin",
                "server": server_name,
                "schema": tool
            }
            self.schema_cache[tool["name"]] = tool
    
    def register_skill(self, skill_name: str, skill_def: SkillDefinition):
        """注册 Skill（由 SkillLoader 调用）"""
        self.tool_registry[skill_name] = {
            "source": "skill",
            "skill_def": skill_def
        }
        self.schema_cache[skill_name] = {
            "name": skill_name,
            "description": skill_def.description,
            "inputSchema": skill_def.parameters
        }

## 四、双轨系统对比总结
| 维度       | 内置 MCP 工具    | 外部 Skill 加载 |
| -------- | ------------ | ----------- |
| **定位**   | 招聘核心引擎       | 通用能力扩展      |
| **稳定性**  | ★★★★★        | ★★★☆☆       |
| **灵活性**  | ★★☆☆☆        | ★★★★★       |
| **性能**   | ★★★★★        | ★★★☆☆       |
| **隔离性**  | ★★☆☆☆        | ★★★★★       |
| **社区共享** | ★☆☆☆☆        | ★★★★★       |
| **热更新**  | ★☆☆☆☆        | ★★★★★       |
| **适用场景** | 候选人/职位/面试/评估 | 天气/搜索/地图/邮件 |

## 五、落地建议

### 第一阶段：内置工具（已完成）

- ✅ 37个工具已定义
    
- ✅ 10个 MCP Server 已规划
    
- 🔄 逐个实现 Server 代码
    

### 第二阶段：Skill 基础设施

1. 实现 `SkillLoader` 类
    
2. 定义 `SKILL.md` 解析器
    
3. 实现子进程隔离执行
    
4. 添加 CLI 管理命令
    

### 第三阶段：社区 Skill 生态

1. 创建官方 Skill 仓库
    
2. 编写 Skill 开发文档
    
3. 提供 Skill 模板生成器
    
4. 建立 Skill 审核机制



