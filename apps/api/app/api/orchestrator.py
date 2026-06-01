"""Orchestrator API — LangGraph orchestrator_graph (Phase V).

流程:  POST /orchestrator/analyze  → create_orchestrator_graph() (LangGraph)

新流程特性:
- StateGraph 编排（intent_recognition → execute_<agent> → END）
- 每次 invoke 创建 thread_id 写入 checkpointer
- HumanLoop 触发由 graph 状态机接管（Phase U 落地）
- /tasks/{id}/timeline + /tasks/{id}/snapshots 可观察完整执行历史
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import settings
from app.graphs.orchestrator_graph import create_orchestrator_graph

logger = logging.getLogger(__name__)

router = APIRouter()

_graph = None


def _build_checkpointer():
    """选择 checkpointer — PostgresSaver (生产) 或 MemorySaver (开发)。

    PostgresSaver 需要 LANGGRAPH_PG_DSN env var (psycopg3 格式)。
    首次使用会调用 setup() 自动建表（CREATE TABLE IF NOT EXISTS）。
    未设置时降级到 MemorySaver — 进程重启丢失状态。
    """
    dsn = settings.langgraph_pg_dsn
    if dsn:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            saver = PostgresSaver.from_conn_string(dsn)
            saver.setup()
            logger.info("LangGraph: using PostgresSaver (DSN=%s...)", dsn[:24])
            return saver
        except Exception as e:
            logger.error("PostgresSaver init failed, falling back to MemorySaver: %s", e)
    logger.info("LangGraph: using MemorySaver (LANGGRAPH_PG_DSN not set or init failed)")
    return MemorySaver()


def _get_graph():
    global _graph
    if _graph is None:
        _graph = create_orchestrator_graph(checkpointer=_build_checkpointer())
    return _graph


def reset_graph_cache() -> None:
    """测试用 — 重置懒加载的 graph，让 _build_checkpointer 重新跑。"""
    global _graph
    _graph = None


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
    """走 LangGraph orchestrator_graph。

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
