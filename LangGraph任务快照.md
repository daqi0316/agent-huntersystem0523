我来为你设计一套基于 LangGraph 的 AI 招聘系统完整规划，重点解决**长程任务状态管理、快照创建与恢复**问题。

---

## 一、LangGraph 核心架构设计

### 1. 整体架构图
┌─────────────────────────────────────────────────────────────────┐
│                        用户交互层                                │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │ AI 对话入口   │  │ 管理后台界面  │                            │
│  │ (默认路径)     │  │ (隐藏/兜底)   │                            │
│  └──────┬───────┘  └──────┬───────┘                            │
│         └─────────────────┘                                     │
│                   ↓                                             │
├─────────────────────────────────────────────────────────────────┤
│                      编排层 (Orchestrator)                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  意图识别 → Agent 路由 → 结果聚合 → 状态快照管理          │   │
│  │  [StateGraph] 主控图，管理所有子图的生命周期              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                   ↓                                             │
├─────────────────────────────────────────────────────────────────┤
│                    业务 Agent 层 (6个并行子图)                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ │
│  │简历解析  │ │ 寻访    │ │ 筛选    │ │ 面试协调 │ │ 薪酬谈判 │ │
│  │ Agent   │ │ Agent   │ │ Agent   │ │ Agent   │ │ Agent   │ │
│  │ (子图)   │ │ (子图)   │ │ (子图)   │ │ (子图)   │ │ (子图)   │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ │
│  ┌─────────┐                                                    │
│  │ 入职跟进 │  ← 每个子图内部都有 Checkpoint + 状态快照         │
│  │ Agent   │     支持断点恢复、任务重启、错误重试                │
│  │ (子图)   │                                                    │
│  └─────────┘                                                    │
├─────────────────────────────────────────────────────────────────┤
│                      共享层 (Shared Layer)                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              │
│  │ 记忆工具 │ │ 知识工具 │ │ 通知工具 │ │ 权限工具 │              │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘              │
├─────────────────────────────────────────────────────────────────┤
│                      MCP Server 层                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              │
│  │ 简历解析 │ │ 职位发布 │ │ 邮件发送 │ │ 日历管理 │              │
│  │ MCP工具  │ │ MCP工具  │ │ MCP工具  │ │ MCP工具  │              │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘              │
├─────────────────────────────────────────────────────────────────┤
│                   业务系统 API + 数据库                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              │
│  │ 候选人库 │ │ 职位库   │ │ 面试记录 │ │ 薪酬数据 │              │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘              │
└─────────────────────────────────────────────────────────────────┘

## 二、状态快照系统设计（核心）

### 2.1 状态数据结构定义
# state.py - 核心状态定义
from typing import TypedDict, Annotated, List, Dict, Optional, Any
from datetime import datetime
from enum import Enum
import operator

class TaskStatus(str, Enum):
    PENDING = "pending"           # 等待执行
    RUNNING = "running"           # 执行中
    PAUSED = "paused"             # 用户暂停
    COMPLETED = "completed"       # 完成
    FAILED = "failed"             # 失败
    RECOVERED = "recovered"       # 从快照恢复

class AgentType(str, Enum):
    RESUME_PARSER = "resume_parser"
    SOURCING = "sourcing"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    ONBOARDING = "onboarding"

# ========== 核心：长程任务状态 ==========
class TaskState(TypedDict):
    """
    每个招聘任务的全局状态
    支持序列化保存到数据库，用于快照恢复
    """
    # === 任务标识 ===
    task_id: str                          # 唯一任务ID (UUID)
    job_id: str                           # 关联职位ID
    user_id: str                          # 操作人ID
    created_at: str                       # 创建时间 ISO格式
    updated_at: str                       # 更新时间
    
    # === 执行状态 ===
    current_agent: Optional[AgentType]    # 当前执行中的Agent
    status: TaskStatus                    # 整体任务状态
    execution_history: Annotated[List[Dict], operator.add]  # 执行历史
    
    # === 各Agent子状态（关键：每个子图有自己的状态）===
    resume_parser_state: Optional[Dict]    # 简历解析状态
    sourcing_state: Optional[Dict]        # 寻访状态
    screening_state: Optional[Dict]        # 筛选状态
    interview_state: Optional[Dict]      # 面试状态
    offer_state: Optional[Dict]          # 薪酬状态
    onboarding_state: Optional[Dict]       # 入职状态
    
    # === 共享数据 ===
    candidates: Annotated[List[Dict], operator.add]  # 候选人列表
    messages: Annotated[List[Dict], operator.add]      # 对话消息
    shared_memory: Dict                                  # 共享记忆
    
    # === 错误与恢复 ===
    error_info: Optional[Dict]            # 错误信息
    snapshot_id: Optional[str]            # 最后一次快照ID
    recovery_count: int                   # 恢复次数

# ========== 子图状态示例：简历解析 ==========
class ResumeParserState(TypedDict):
    sub_task_id: str
    status: TaskStatus
    current_step: str                     # 当前步骤：upload/parse/extract/verify
    resume_file: Optional[str]            # 简历文件路径
    parsed_data: Optional[Dict]           # 解析结果
    extracted_skills: List[str]           # 提取的技能
    match_score: Optional[float]          # 匹配分数
    step_history: Annotated[List[Dict], operator.add]
    error: Optional[str]
### 2.2 状态快照管理器
# snapshot_manager.py
import json
import hashlib
from datetime import datetime
from typing import Optional, Dict, List
import sqlite3  # 或 PostgreSQL / Redis

class SnapshotManager:
    """
    状态快照管理器
    负责：创建快照、保存到持久化存储、按ID恢复、列出历史快照
    """
    
    def __init__(self, db_path: str = "snapshots.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化快照表"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                parent_snapshot_id TEXT,
                state_json TEXT NOT NULL,
                state_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                agent_type TEXT,
                step_name TEXT,
                description TEXT,
                is_auto INTEGER DEFAULT 1,  -- 1=自动, 0=手动
                tags TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_id ON snapshots(task_id)
        """)
        conn.commit()
        conn.close()
    
    def create_snapshot(
        self, 
        state: Dict, 
        task_id: str,
        agent_type: Optional[str] = None,
        step_name: Optional[str] = None,
        description: str = "",
        is_auto: bool = True,
        parent_snapshot_id: Optional[str] = None
    ) -> str:
        """
        创建状态快照
        返回: snapshot_id
        """
        # 生成唯一ID
        timestamp = datetime.now().isoformat()
        state_json = json.dumps(state, ensure_ascii=False, sort_keys=True)
        state_hash = hashlib.sha256(state_json.encode()).hexdigest()[:16]
        snapshot_id = f"{task_id}_{agent_type or 'global'}_{state_hash}"
        
        # 保存到数据库
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO snapshots 
            (snapshot_id, task_id, parent_snapshot_id, state_json, state_hash, 
             created_at, agent_type, step_name, description, is_auto)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_id, task_id, parent_snapshot_id, state_json, state_hash,
            timestamp, agent_type, step_name, description, 1 if is_auto else 0
        ))
        conn.commit()
        conn.close()
        
        return snapshot_id
    
    def restore_snapshot(self, snapshot_id: str) -> Optional[Dict]:
        """通过快照ID恢复状态"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT state_json FROM snapshots WHERE snapshot_id = ?", 
            (snapshot_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return json.loads(row[0])
        return None
    
    def get_snapshots_by_task(
        self, 
        task_id: str,
        agent_type: Optional[str] = None
    ) -> List[Dict]:
        """获取任务的所有快照，支持按Agent类型筛选"""
        conn = sqlite3.connect(self.db_path)
        if agent_type:
            cursor = conn.execute(
                """SELECT snapshot_id, created_at, agent_type, step_name, 
                          description, is_auto 
                   FROM snapshots 
                   WHERE task_id = ? AND agent_type = ?
                   ORDER BY created_at DESC""",
                (task_id, agent_type)
            )
        else:
            cursor = conn.execute(
                """SELECT snapshot_id, created_at, agent_type, step_name, 
                          description, is_auto 
                   FROM snapshots 
                   WHERE task_id = ?
                   ORDER BY created_at DESC""",
                (task_id,)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "snapshot_id": r[0],
                "created_at": r[1],
                "agent_type": r[2],
                "step_name": r[3],
                "description": r[4],
                "is_auto": bool(r[5])
            }
            for r in rows
        ]
    
    def get_latest_snapshot(self, task_id: str) -> Optional[Dict]:
        """获取任务最新快照"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """SELECT state_json, snapshot_id FROM snapshots 
               WHERE task_id = ? ORDER BY created_at DESC LIMIT 1""",
            (task_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "state": json.loads(row[0]),
                "snapshot_id": row[1]
            }
        return None

## 三、LangGraph 主图与子图实现

### 3.1 主编排图（Orchestrator）
# orchestrator_graph.py
from typing import Literal, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode

from state import TaskState, TaskStatus, AgentType
from snapshot_manager import SnapshotManager

# 导入各子图
from agents.resume_parser_graph import create_resume_parser_graph
from agents.sourcing_graph import create_sourcing_graph
from agents.screening_graph import create_screening_graph
from agents.interview_graph import create_interview_graph
from agents.offer_graph import create_offer_graph
from agents.onboarding_graph import create_onboarding_graph

class Orchestrator:
    """
    主编排器
    管理整个招聘任务的生命周期，包括状态快照
    """
    
    def __init__(self):
        self.snapshot_manager = SnapshotManager()
        self.graph = self._build_graph()
        self.subgraphs = {
            AgentType.RESUME_PARSER: create_resume_parser_graph(),
            AgentType.SOURCING: create_sourcing_graph(),
            AgentType.SCREENING: create_screening_graph(),
            AgentType.INTERVIEW: create_interview_graph(),
            AgentType.OFFER: create_offer_graph(),
            AgentType.ONBOARDING: create_onboarding_graph(),
        }
    
    def _build_graph(self) -> StateGraph:
        """构建主状态图"""
        builder = StateGraph(TaskState)
        
        # === 节点定义 ===
        builder.add_node("intent_recognition", self._intent_recognition)
        builder.add_node("route_agent", self._route_agent)
        builder.add_node("execute_subgraph", self._execute_subgraph)
        builder.add_node("aggregate_results", self._aggregate_results)
        builder.add_node("create_snapshot", self._create_snapshot_node)
        builder.add_node("error_handler", self._error_handler)
        builder.add_node("pause_handler", self._pause_handler)
        builder.add_node("recovery_handler", self._recovery_handler)
        
        # === 入口 ===
        builder.set_entry_point("intent_recognition")
        
        # === 条件边 ===
        builder.add_conditional_edges(
            "intent_recognition",
            self._decide_next,
            {
                "route": "route_agent",
                "pause": "pause_handler",
                "recover": "recovery_handler",
                "error": "error_handler"
            }
        )
        
        builder.add_conditional_edges(
            "route_agent",
            self._select_agent,
            {
                "resume_parser": "execute_subgraph",
                "sourcing": "execute_subgraph",
                "screening": "execute_subgraph",
                "interview": "execute_subgraph",
                "offer": "execute_subgraph",
                "onboarding": "execute_subgraph",
                "complete": END
            }
        )
        
        # 子图执行后：创建快照 → 聚合结果 → 继续路由
        builder.add_edge("execute_subgraph", "create_snapshot")
        builder.add_edge("create_snapshot", "aggregate_results")
        builder.add_edge("aggregate_results", "intent_recognition")
        
        # 错误处理：创建快照 → 重试或结束
        builder.add_edge("error_handler", "create_snapshot")
        builder.add_conditional_edges(
            "error_handler",
            self._decide_retry,
            {"retry": "route_agent", "end": END}
        )
        
        # 暂停处理：创建快照 → 等待恢复
        builder.add_edge("pause_handler", "create_snapshot")
        builder.add_edge("pause_handler", END)
        
        # 恢复处理：从快照加载 → 继续执行
        builder.add_edge("recovery_handler", "route_agent")
        
        return builder.compile(
            checkpointer=SqliteSaver.from_conn_string("checkpoints.db"),
            interrupt_before=["execute_subgraph"]  # 支持人工审批点
        )
    
    def _intent_recognition(self, state: TaskState) -> Dict:
        """意图识别：解析用户输入，决定下一步"""
        # 这里接入LLM进行意图识别
        # 简化示例：
        last_message = state["messages"][-1] if state["messages"] else {}
        content = last_message.get("content", "")
        
        # 检测恢复指令
        if "恢复" in content or "recover" in content.lower():
            return {"status": TaskStatus.PENDING, "next_action": "recover"}
        
        # 检测暂停指令
        if "暂停" in content or "pause" in content.lower():
            return {"status": TaskStatus.PAUSED, "next_action": "pause"}
        
        # 正常路由
        return {"status": TaskStatus.RUNNING, "next_action": "route"}
    
    def _route_agent(self, state: TaskState) -> Dict:
        """根据当前状态决定路由到哪个Agent"""
        # 如果已有当前Agent，继续执行
        if state.get("current_agent"):
            return {"current_agent": state["current_agent"]}
        
        # 否则根据任务进度智能路由
        if not state.get("resume_parser_state"):
            return {"current_agent": AgentType.RESUME_PARSER}
        elif not state.get("sourcing_state"):
            return {"current_agent": AgentType.SOURCING}
        # ... 以此类推
        
        return {"current_agent": None}  # 所有完成
    
    def _execute_subgraph(self, state: TaskState) -> Dict:
        """
        执行子图（关键：子图内部也有快照）
        """
        agent_type = state["current_agent"]
        subgraph = self.subgraphs[agent_type]
        
        # 准备子图输入状态
        sub_state = state.get(f"{agent_type}_state", {})
        
        # 执行子图（子图内部会自动创建快照）
        result = subgraph.invoke(sub_state)
        
        # 更新主状态
        update_key = f"{agent_type}_state"
        return {
            update_key: result,
            "execution_history": [{
                "agent": agent_type,
                "timestamp": datetime.now().isoformat(),
                "result_summary": result.get("summary", "")
            }]
        }
    
    def _create_snapshot_node(self, state: TaskState) -> Dict:
        """
        自动创建全局状态快照
        在每个关键步骤后自动调用
        """
        snapshot_id = self.snapshot_manager.create_snapshot(
            state=dict(state),
            task_id=state["task_id"],
            agent_type=state.get("current_agent"),
            step_name=state.get("status"),
            description=f"Auto snapshot at {state['status']}",
            is_auto=True
        )
        
        return {
            "snapshot_id": snapshot_id,
            "updated_at": datetime.now().isoformat()
        }
    
    def _recovery_handler(self, state: TaskState) -> Dict:
        """
        从快照恢复状态
        用户可以通过 snapshot_id 指定恢复点
        """
        # 从用户消息中提取 snapshot_id
        last_message = state["messages"][-1]
        content = last_message.get("content", "")
        
        # 解析 snapshot_id（简化，实际可用正则）
        # 格式: "恢复 snapshot_xxx" 或 "recover xxx"
        snapshot_id = self._extract_snapshot_id(content)
        
        if not snapshot_id:
            # 使用最新快照
            latest = self.snapshot_manager.get_latest_snapshot(state["task_id"])
            if latest:
                recovered_state = latest["state"]
                snapshot_id = latest["snapshot_id"]
            else:
                return {"error_info": {"message": "No snapshot found"}}
        else:
            recovered_state = self.snapshot_manager.restore_snapshot(snapshot_id)
        
        if not recovered_state:
            return {"error_info": {"message": f"Snapshot {snapshot_id} not found"}}
        
        # 恢复状态，增加恢复计数
        recovered_state["status"] = TaskStatus.RECOVERED
        recovered_state["recovery_count"] = recovered_state.get("recovery_count", 0) + 1
        recovered_state["messages"] = state["messages"]  # 保留最新消息
        
        return recovered_state
    
    def _extract_snapshot_id(self, content: str) -> Optional[str]:
        """从消息中提取 snapshot_id"""
        import re
        match = re.search(r'snapshot_[\w_]+', content)
        return match.group(0) if match else None
    
    def _decide_next(self, state: TaskState) -> Literal["route", "pause", "recover", "error"]:
        """决定下一步走向"""
        if state.get("status") == TaskStatus.PAUSED:
            return "pause"
        if state.get("status") == TaskStatus.RECOVERED:
            return "route"
        if state.get("error_info"):
            return "error"
        if "恢复" in str(state.get("messages", [])):
            return "recover"
        return "route"
    
    def _select_agent(self, state: TaskState) -> Literal[
        "resume_parser", "sourcing", "screening", 
        "interview", "offer", "onboarding", "complete"
    ]:
        """选择具体Agent"""
        agent = state.get("current_agent")
        if not agent:
            return "complete"
        return agent
    
    def _aggregate_results(self, state: TaskState) -> Dict:
        """聚合各Agent结果"""
        # 汇总所有子状态到共享层
        all_candidates = []
        for agent_type in AgentType:
            sub_state = state.get(f"{agent_type}_state", {})
            if sub_state and "candidates" in sub_state:
                all_candidates.extend(sub_state["candidates"])
        
        return {
            "candidates": all_candidates,
            "status": TaskStatus.RUNNING if state.get("current_agent") else TaskStatus.COMPLETED
        }
    
    def _error_handler(self, state: TaskState) -> Dict:
        """错误处理"""
        error = state.get("error_info", {})
        # 记录错误，准备重试
        return {
            "error_info": {**error, "handled_at": datetime.now().isoformat()},
            "status": TaskStatus.RUNNING
        }
    
    def _decide_retry(self, state: TaskState) -> Literal["retry", "end"]:
        """决定是否重试"""
        recovery_count = state.get("recovery_count", 0)
        if recovery_count < 3:  # 最多重试3次
            return "retry"
        return "end"
    
    def _pause_handler(self, state: TaskState) -> Dict:
        """暂停处理"""
        return {
            "status": TaskStatus.PAUSED,
            "pause_reason": "user_requested"
        }
    
    # ========== 公共API ==========
    def run_task(self, initial_state: TaskState) -> TaskState:
        """启动新任务"""
        return self.graph.invoke(initial_state)
    
    def resume_task(self, task_id: str, snapshot_id: Optional[str] = None) -> TaskState:
        """恢复任务"""
        # 从快照恢复后继续执行
        if snapshot_id:
            state = self.snapshot_manager.restore_snapshot(snapshot_id)
        else:
            latest = self.snapshot_manager.get_latest_snapshot(task_id)
            state = latest["state"] if latest else None
        
        if not state:
            raise ValueError(f"No state found for task {task_id}")
        
        # 添加恢复消息
        state["messages"].append({
            "role": "system",
            "content": f"恢复任务，snapshot_id: {snapshot_id or 'latest'}"
        })
        
        return self.graph.invoke(state)
    
    def get_task_snapshots(self, task_id: str) -> List[Dict]:
        """获取任务快照列表"""
        return self.snapshot_manager.get_snapshots_by_task(task_id)
### 3.2 子图示例：简历解析 Agent
# agents/resume_parser_graph.py
from typing import Dict, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from state import ResumeParserState, TaskStatus
from snapshot_manager import SnapshotManager

def create_resume_parser_graph():
    """创建简历解析子图（带内部状态快照）"""
    
    builder = StateGraph(ResumeParserState)
    snapshot_mgr = SnapshotManager(db_path="resume_snapshots.db")
    
    # === 步骤节点 ===
    def step_upload(state: ResumeParserState) -> Dict:
        """步骤1：接收简历文件"""
        # 实际：调用文件上传工具
        return {
            "current_step": "upload",
            "status": TaskStatus.RUNNING
        }
    
    def step_parse(state: ResumeParserState) -> Dict:
        """步骤2：解析PDF/DOCX"""
        # 实际：调用PDF解析工具
        return {
            "current_step": "parse",
            "status": TaskStatus.RUNNING
        }
    
    def step_extract(state: ResumeParserState) -> Dict:
        """步骤3：提取关键信息"""
        # 实际：调用LLM提取技能、经验等
        return {
            "current_step": "extract",
            "extracted_skills": ["Python", "React", "LangChain"],
            "status": TaskStatus.RUNNING
        }
    
    def step_verify(state: ResumeParserState) -> Dict:
        """步骤4：验证结果"""
        # 实际：验证提取质量
        return {
            "current_step": "verify",
            "status": TaskStatus.COMPLETED
        }
    
    def create_sub_snapshot(state: ResumeParserState) -> Dict:
        """创建子图内部快照"""
        snapshot_id = snapshot_mgr.create_snapshot(
            state=dict(state),
            task_id=state["sub_task_id"],
            agent_type="resume_parser",
            step_name=state["current_step"],
            description=f"Resume parser step: {state['current_step']}",
            is_auto=True
        )
        return {"last_snapshot_id": snapshot_id}
    
    def error_recovery(state: ResumeParserState) -> Dict:
        """错误恢复"""
        # 回退到上一步快照
        snapshots = snapshot_mgr.get_snapshots_by_task(
            state["sub_task_id"], 
            agent_type="resume_parser"
        )
        if len(snapshots) >= 2:
            # 回退到倒数第二个快照
            prev_snapshot = snapshots[1]  # [0]是最新的（当前失败的）
            recovered = snapshot_mgr.restore_snapshot(prev_snapshot["snapshot_id"])
            recovered["status"] = TaskStatus.RUNNING
            recovered["error"] = None
            return recovered
        
        return {"status": TaskStatus.FAILED, "error": "No previous snapshot to recover"}
    
    # === 构建图 ===
    builder.add_node("upload", step_upload)
    builder.add_node("parse", step_parse)
    builder.add_node("extract", step_extract)
    builder.add_node("verify", step_verify)
    builder.add_node("snapshot", create_sub_snapshot)
    builder.add_node("error_recovery", error_recovery)
    
    # 顺序执行：upload → snapshot → parse → snapshot → extract → snapshot → verify → snapshot
    builder.set_entry_point("upload")
    builder.add_edge("upload", "snapshot")
    builder.add_edge("snapshot", "parse")
    builder.add_edge("parse", "snapshot")
    builder.add_edge("snapshot", "extract")
    builder.add_edge("extract", "snapshot")
    builder.add_edge("snapshot", "verify")
    builder.add_edge("verify", "snapshot")
    builder.add_edge("snapshot", END)
    
    # 错误处理：任何步骤出错 → error_recovery → 重试或结束
    builder.add_conditional_edges(
        "upload", 
        lambda s: "error" if s.get("error") else "continue",
        {"error": "error_recovery", "continue": "snapshot"}
    )
    # ... 其他步骤类似
    
    return builder.compile(
        checkpointer=SqliteSaver.from_conn_string("resume_checkpoints.db")
    )

## 四、快照恢复与任务重启机制

### 4.1 恢复场景矩阵
| 场景          | 触发方式                     | 恢复策略            |
| ----------- | ------------------------ | --------------- |
| **系统崩溃**    | 服务重启后自动检测                | 加载最新自动快照，从断点继续  |
| **用户暂停**    | 用户发送"暂停"                 | 创建暂停快照，任务挂起     |
| **用户恢复**    | 用户发送"恢复 \[snapshot\_id]" | 加载指定快照，继续执行     |
| **Agent失败** | 子图执行异常                   | 回退到子图上一步快照，重试3次 |
| **人工审批**    | 到达interrupt节点            | 等待用户输入，从断点继续    |
| **定时任务**    | 定时器触发                    | 加载指定任务的最新快照执行   |
### 4.2 恢复命令示例
# 用户交互层代码示例
class UserInterface:
    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator
    
    async def handle_message(self, user_id: str, message: str):
        """处理用户消息"""
        
        # 1. 解析恢复指令
        if message.startswith("恢复") or message.startswith("recover"):
            # 提取 snapshot_id
            parts = message.split()
            snapshot_id = parts[1] if len(parts) > 1 else None
            
            # 获取任务ID（从上下文或用户状态）
            task_id = self._get_user_active_task(user_id)
            
            # 执行恢复
            result = self.orchestrator.resume_task(task_id, snapshot_id)
            return f"任务已恢复，当前状态: {result['status']}"
        
        # 2. 解析暂停指令
        if message.startswith("暂停") or message.startswith("pause"):
            task_id = self._get_user_active_task(user_id)
            # 发送暂停信号（通过状态更新）
            # 实际通过更新任务状态实现
            return "任务已暂停，可随时恢复"
        
        # 3. 查看快照列表
        if message.startswith("快照") or message.startswith("snapshots"):
            task_id = self._get_user_active_task(user_id)
            snapshots = self.orchestrator.get_task_snapshots(task_id)
            
            response = "📸 任务快照列表:\n"
            for snap in snapshots[:10]:  # 最近10个
                auto_mark = "🤖" if snap["is_auto"] else "👤"
                response += f"{auto_mark} `{snap['snapshot_id']}`\n"
                response += f"   时间: {snap['created_at']}\n"
                response += f"   步骤: {snap['agent_type']} - {snap['step_name']}\n"
                response += f"   描述: {snap['description']}\n\n"
            
            return response
        
        # 4. 正常任务消息
        # ... 创建或继续任务
### 4.3 快照可视化时间线
任务: JOB-2024-001 (招聘高级Java工程师)

时间线:
16:00:00 🤖 [AUTO] 任务创建          snapshot_JOB001_global_a1b2c3d4
16:00:05 🤖 [AUTO] 简历解析-上传完成   snapshot_JOB001_resume_parser_e5f6g7h8
16:00:12 🤖 [AUTO] 简历解析-解析完成   snapshot_JOB001_resume_parser_i9j0k1l2
16:00:30 👤 [MANUAL] 用户暂停        snapshot_JOB001_global_m3n4o5p6
         [任务暂停，等待恢复...]
16:30:00 👤 [MANUAL] 用户恢复          ← 从 snapshot_JOB001_global_m3n4o5p6 恢复
16:30:05 🤖 [AUTO] 寻访-开始搜索       snapshot_JOB001_sourcing_q7r8s9t0
16:35:20 🤖 [AUTO] 寻访-找到5人        snapshot_JOB001_sourcing_u1v2w3x4
16:35:25 ❌ [ERROR] 筛选Agent超时失败
16:35:26 🤖 [AUTO] 自动回退            ← 回退到 snapshot_JOB001_sourcing_u1v2w3x4
16:35:30 🤖 [AUTO] 筛选-重试           snapshot_JOB001_screening_y5z6a7b8
16:40:00 🤖 [AUTO] 筛选-完成3人        snapshot_JOB001_screening_c9d0e1f2

## 五、MCP 工具系统集成

### 5.1 工具注册表
# mcp_tools/registry.py
from typing import Dict, Callable, Any

class MCPToolRegistry:
    """MCP工具注册表，供所有Agent共享"""
    
    def __init__(self):
        self.tools: Dict[str, Dict] = {}
    
    def register(self, name: str, tool: Callable, description: str, agent_types: list):
        self.tools[name] = {
            "function": tool,
            "description": description,
            "allowed_agents": agent_types
        }
    
    def get_tools_for_agent(self, agent_type: str) -> Dict[str, Callable]:
        """获取Agent可用的工具"""
        return {
            name: info["function"] 
            for name, info in self.tools.items()
            if agent_type in info["allowed_agents"]
        }

# 初始化注册表
registry = MCPToolRegistry()

# 注册简历解析工具
registry.register(
    "parse_resume_pdf",
    parse_pdf_tool,
    "解析PDF简历，提取文本和结构",
    ["resume_parser"]
)

registry.register(
    "search_candidates",
    search_db_tool,
    "从候选人数据库搜索匹配人选",
    ["sourcing", "screening"]
)

registry.register(
    "send_email",
    send_email_tool,
    "发送邮件通知",
    ["interview", "offer", "onboarding"]
)

# ... 其他工具

## 六、部署与配置建议

### 6.1 项目结构
ai-recruitment-langgraph/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI入口
│   └── api/
│       ├── tasks.py            # 任务管理API
│       ├── snapshots.py        # 快照管理API
│       └── websocket.py        # 实时状态推送
├── core/
│   ├── state.py                # 状态定义
│   ├── snapshot_manager.py     # 快照管理器
│   └── config.py               # 配置
├── graphs/
│   ├── orchestrator.py         # 主编排图
│   └── agents/
│       ├── resume_parser.py    # 简历解析子图
│       ├── sourcing.py         # 寻访子图
│       ├── screening.py        # 筛选子图
│       ├── interview.py        # 面试子图
│       ├── offer.py            # 薪酬子图
│       └── onboarding.py       # 入职子图
├── mcp_tools/
│   ├── registry.py             # 工具注册
│   ├── resume_tools.py         # 简历相关MCP
│   ├── search_tools.py         # 搜索相关MCP
│   └── notification_tools.py   # 通知相关MCP
├── shared/
│   ├── memory.py               # 共享记忆
│   ├── knowledge.py            # 知识库
│   └── permissions.py          # 权限控制
├── storage/
│   ├── snapshots.db            # SQLite快照存储
│   └── checkpoints.db          # LangGraph检查点
├── tests/
└── requirements.txt
### 6.2 关键依赖
langgraph>=0.1.0
langchain>=0.2.0
langchain-openai>=0.1.0
sqlite3  # 内置
pydantic>=2.0
fastapi>=0.110.0
uvicorn>=0.27.0

## 七、使用流程示例
# 完整使用示例
from core.state import TaskState, TaskStatus
from graphs.orchestrator import Orchestrator

# 1. 初始化编排器
orch = Orchestrator()

# 2. 创建新任务
initial_state = TaskState(
    task_id="JOB-2024-001",
    job_id="JAVA-SENIOR-001",
    user_id="HR-001",
    created_at="2024-05-31T16:00:00",
    updated_at="2024-05-31T16:00:00",
    status=TaskStatus.PENDING,
    current_agent=None,
    execution_history=[],
    resume_parser_state=None,
    sourcing_state=None,
    screening_state=None,
    interview_state=None,
    offer_state=None,
    onboarding_state=None,
    candidates=[],
    messages=[{
        "role": "user",
        "content": "开始招聘高级Java工程师，帮我解析这批简历"
    }],
    shared_memory={},
    error_info=None,
    snapshot_id=None,
    recovery_count=0
)

# 3. 启动任务（自动执行，内部自动创建快照）
result = orch.run_task(initial_state)

# 4. 用户查看快照
snapshots = orch.get_task_snapshots("JOB-2024-001")
print(f"已创建 {len(snapshots)} 个快照")

# 5. 用户暂停后恢复
# 用户发送: "恢复 snapshot_JOB-2024-001_resume_parser_a1b2c3d4"
recovered_result = orch.resume_task(
    "JOB-2024-001", 
    snapshot_id="snapshot_JOB-2024-001_resume_parser_a1b2c3d4"
)

# 6. 系统崩溃后自动恢复
# 服务重启时，扫描所有RUNNING状态任务
# 自动加载最新快照继续执行

这套设计的核心优势：

1. **分层快照**：全局快照（主图）+ 局部快照（子图），支持精确恢复
    
2. **自动+手动**：系统自动在每个步骤后创建快照，用户也可手动触发
    
3. **快速定位**：通过 `snapshot_id` 直接定位到任意历史状态
    
4. **断点续传**：支持系统崩溃、服务重启后的自动恢复
    
5. **LangGraph原生**：利用 `checkpointer` 和 `interrupt` 机制实现