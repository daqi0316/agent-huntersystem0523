"""Tasks API — LangGraph 编排任务管理。

POST   /tasks               — 创建新任务（invoke orchestrator graph）
GET    /tasks               — 列出当前用户的任务
GET    /tasks/{id}          — 任务状态（从 OperationLog 汇总）
GET    /tasks/{id}/timeline — 快照时间线（从 OperationLog 升序）
GET    /tasks/{id}/snapshots — LangGraph checkpoint 历史（从 MemorySaver 读）
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func
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
        _graph = create_orchestrator_graph(checkpointer=MemorySaver())
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


@router.get("")
async def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户参与过的任务（按 task_id 分组，从 OperationLog 聚合）。

    注: 任务本身的 state 在 MemorySaver 中；OperationLog 是审计/事件流。
    这里 list 返回最近 N 个 distinct task_id 的最新事件，方便前端做列表。
    """
    distinct_task = (
        select(
            OperationLog.metadata_json["task_id"].as_string().label("task_id"),
            func.max(OperationLog.created_at).label("last_event_at"),
            func.max(OperationLog.action).label("last_action"),
            func.max(OperationLog.agent_name).label("last_agent"),
        )
        .where(OperationLog.metadata_json["user_id"].as_string() == user_id)
        .group_by(OperationLog.metadata_json["task_id"].as_string())
        .order_by(desc("last_event_at"))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(distinct_task)
    rows = result.all()
    return success({
        "tasks": [
            {
                "task_id": r.task_id,
                "last_event_at": r.last_event_at.isoformat() if r.last_event_at else "",
                "last_action": r.last_action,
                "last_agent": r.last_agent,
            }
            for r in rows
        ],
        "skip": skip,
        "limit": limit,
        "count": len(rows),
    })


@router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """获取任务状态（从 OperationLog 查询最近 20 条执行记录）。"""
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
    """快照时间线 — 从 OperationLog 按 task_id 升序查询。"""
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


@router.get("/{task_id}/snapshots")
async def task_snapshots(task_id: str):
    """LangGraph checkpoint 历史（MemorySaver）。

    进程重启后历史会丢失 — 后续 S.4.x 切到 PostgresSaver 后持久。
    失败时返回空数组（容错：MemorySaver 状态可能已 evict）。
    """
    try:
        graph = _get_graph()
        config = {"configurable": {"thread_id": task_id}}
        history = list(graph.get_state_history(config))
    except Exception as e:
        logger.warning("get_state_history failed for %s: %s", task_id, e)
        history = []

    snapshots = []
    for i, state in enumerate(history):
        values = state.values if hasattr(state, "values") else {}
        metadata = state.metadata if hasattr(state, "metadata") else {}
        next_nodes = state.next if hasattr(state, "next") else []
        snapshots.append({
            "index": i,
            "step": metadata.get("step", i),
            "intent": values.get("intent"),
            "status": values.get("status"),
            "error": values.get("error"),
            "next": list(next_nodes) if next_nodes else [],
            "checkpoint_id": (
                state.config["configurable"].get("checkpoint_id", "")
                if hasattr(state, "config") and state.config
                else ""
            ),
        })
    return success({"task_id": task_id, "snapshots": snapshots, "total": len(snapshots)})
