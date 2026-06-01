"""Tasks API — LangGraph 编排任务管理。

POST   /tasks               — 创建新任务（invoke orchestrator graph）
GET    /tasks/{id}          — 任务状态
GET    /tasks/{id}/timeline — 快照时间线（从 OperationLog 查询）
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.core.response import success, error
from app.graphs.orchestrator_graph import create_orchestrator_graph
from app.models.operation_log import OperationLog
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

router = APIRouter()

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = create_orchestrator_graph(checkpointer=MemorySaver(), with_interrupt=True)
    return _graph


@router.post("")
async def create_task(
    input_text: str,
    job_id: str = "",
    user_id: str = Depends(get_current_user_id),
):
    """创建新的编排任务。"""
    task_id = str(uuid.uuid4())
    graph = _get_graph()

    try:
        result = await graph.ainvoke(
            {
                "task_id": task_id,
                "user_id": user_id,
                "job_id": job_id,
                "intent": "",
                "input_text": input_text,
                "agent_result": None,
                "error": None,
                "status": "",
            },
            config={"configurable": {"thread_id": task_id}},
        )
        return success({
            "task_id": task_id,
            "intent": result.get("intent"),
            "status": result.get("status"),
            "agent_result": result.get("agent_result"),
            "error": result.get("error"),
        })
    except Exception as e:
        logger.error("Task execution failed: %s", e)
        return error(f"Task execution failed: {e}", status_code=500)


@router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """获取任务状态（从 OperationLog 查询执行记录）。"""
    result = await db.execute(
        select(OperationLog).where(
            OperationLog.metadata_json["task_id"].as_string() == task_id,
        ).order_by(desc(OperationLog.created_at)).limit(20)
    )
    ops = list(result.scalars().all())
    return success({
        "task_id": task_id,
        "events": [
            {
                "agent_name": op.agent_name,
                "action": op.action,
                "status": op.status.value,
                "created_at": op.created_at.isoformat() if op.created_at else "",
            }
            for op in ops
        ],
    })


@router.get("/{task_id}/timeline")
async def task_timeline(task_id: str, db: AsyncSession = Depends(get_db)):
    """快照时间线 — 从 OperationLog 按 task_id 查询。"""
    result = await db.execute(
        select(OperationLog).where(
            OperationLog.metadata_json["task_id"].as_string() == task_id,
        ).order_by(OperationLog.created_at.asc())
    )
    ops = list(result.scalars().all())
    events = [
        {
            "type": op.status.value,
            "agent": op.agent_name,
            "action": op.action,
            "summary": op.output_summary or op.input_summary or "",
            "duration_ms": op.duration_ms,
            "timestamp": op.created_at.isoformat() if op.created_at else "",
        }
        for op in ops
    ]
    return success({"task_id": task_id, "events": events, "total": len(events)})
