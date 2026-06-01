"""Orchestrator API — 流量切换完成 (Phase S.5)。

新流程:  POST /orchestrator/analyze       → create_orchestrator_graph() (LangGraph)
旧流程:  POST /orchestrator/legacy/analyze → OrchestratorAgent            (保留 1 周作 shim)

切换日期: 2026-06-01
Sunset:   2026-06-08（旧路由删除）

新流程特性:
- StateGraph 编排（intent_recognition → execute_<agent> → END）
- 每次 invoke 创建 thread_id 写入 MemorySaver
- interrupt_before 触发由 HumanLoop 接管（S.4 + Phase U 落地）
- /tasks/{id}/timeline + /tasks/{id}/snapshots 可观察完整执行历史
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from langgraph.checkpoint.memory import MemorySaver

from app.agents.orchestrator_agent import OrchestratorAgent
from app.graphs.orchestrator_graph import create_orchestrator_graph

logger = logging.getLogger(__name__)

router = APIRouter()

# 旧 Agent（保留 1 周作为 legacy shim）
_legacy_agent = OrchestratorAgent(name="orchestrator_legacy")

# 新 Graph（懒加载）
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = create_orchestrator_graph(checkpointer=MemorySaver())
    return _graph


class AnalyzeRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=4000, description="复杂任务描述")
    context: dict | None = Field(None, description="上下文信息（可选）")


class SubTaskResult(BaseModel):
    type: str = ""
    description: str = ""
    status: str = ""
    error: str | None = None
    result: dict = {}


class AnalyzeResponse(BaseModel):
    success: bool = True
    status: str = ""
    total_sub_tasks: int = 0
    succeeded: int = 0
    failed: int = 0
    duration_seconds: float = 0.0
    summary: str = ""
    sub_tasks: list[SubTaskResult] = []


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """新流程 — 走 LangGraph orchestrator_graph。

    流程: intent_recognition → conditional_edge → execute_<agent> → END
    返回格式与旧流程保持一致（含 sub_tasks 包装），便于前端零改动切换。
    """
    task_id = str(uuid.uuid4())
    context = req.context or {}
    graph = _get_graph()

    try:
        result = await graph.ainvoke(
            {
                "task_id": task_id,
                "user_id": "",
                "job_id": context.get("job_id", ""),
                "intent": "",
                "input_text": req.task,
                "agent_result": None,
                "error": None,
                "status": "",
            },
            config={"configurable": {"thread_id": task_id}},
        )
    except Exception as e:
        logger.error("Orchestrator graph failed: %s", e)
        return AnalyzeResponse(
            success=False,
            status="failed",
            summary=f"编排执行异常: {e}",
        )

    intent = result.get("intent") or "chat"
    status_raw = result.get("status") or "completed"
    agent_result = result.get("agent_result") or {}
    error = result.get("error")

    sub_tasks_out = [
        SubTaskResult(
            type=intent,
            description=req.task,
            status="completed" if not error else "failed",
            error=error,
            result=agent_result if isinstance(agent_result, dict) else {},
        )
    ]

    succeeded = 0 if error else 1
    failed = 1 if error else 0
    return AnalyzeResponse(
        success=not error,
        status="completed" if not error else "failed",
        total_sub_tasks=1,
        succeeded=succeeded,
        failed=failed,
        duration_seconds=0.0,
        summary=(
            f"Graph 路由意图: {intent} (task_id={task_id[:8]})"
            + (f" — 失败: {error}" if error else "")
        ),
        sub_tasks=sub_tasks_out,
    )


@router.post("/legacy/analyze", response_model=AnalyzeResponse)
async def analyze_legacy(req: AnalyzeRequest, response: Response):
    """[DEPRECATED 2026-06-01, SUNSET 2026-06-08] 旧 OrchestratorAgent 入口。

    新流程已切到 LangGraph orchestrator_graph，请改用 POST /orchestrator/analyze。
    Deprecation 头会让客户端识别 + 渐进迁移。
    """
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-08"
    response.headers["X-Deprecated-By"] = "S.5-traffic-switch"

    result = await _legacy_agent.run({"task": req.task, "context": req.context or {}})

    sub_tasks_out = []
    for st in result.get("sub_tasks", []):
        sub_tasks_out.append(
            SubTaskResult(
                type=st.get("type", ""),
                description=st.get("description", ""),
                status=st.get("status", "unknown"),
            )
        )

    total = result.get("total_sub_tasks", 0)
    succeeded = result.get("succeeded", 0)
    failed = result.get("failed", 0)
    status = result.get("status", "unknown")

    if status == "completed":
        summary = f"编排完成: {total} 个子任务全部成功 ({result.get('duration_seconds', 0)}s)"
    elif status == "partial":
        summary = f"编排部分完成: {succeeded}/{total} 成功, {failed} 失败 ({result.get('duration_seconds', 0)}s)"
    else:
        summary = "编排执行异常"

    return AnalyzeResponse(
        success=status != "failed",
        status=status,
        total_sub_tasks=total,
        succeeded=succeeded,
        failed=failed,
        duration_seconds=result.get("duration_seconds", 0.0),
        summary=summary,
        sub_tasks=sub_tasks_out,
    )
