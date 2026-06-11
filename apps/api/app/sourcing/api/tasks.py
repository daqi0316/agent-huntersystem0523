"""采集任务 CRUD API (P0-9)"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.database import get_db
from app.sourcing.models.crawl_log import CrawlLog
from app.sourcing.orchestrator import SourcingOrchestrator
from app.sourcing.schemas.task import TaskCreate, TaskResponse

router = APIRouter(prefix="/tasks", tags=["sourcing/tasks"])


async def _get_orchestrator(db: AsyncSession = Depends(get_db)):
    from app.core.redis import get_redis
    redis = await get_redis()
    return SourcingOrchestrator(db=db, redis=redis)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreate, orch: SourcingOrchestrator = Depends(_get_orchestrator)):
    task = await orch.create_task(body.model_dump())
    return {"success": True, "data": {"id": task.id, "keyword": task.keyword, "status": task.status}}


@router.get("")
async def list_tasks(
    status_filter: str | None = None,
    platform: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    orch: SourcingOrchestrator = Depends(_get_orchestrator),
):
    tasks, total = await orch.get_task_list(
        status=status_filter, platform=platform, keyword=keyword,
        page=page, page_size=page_size,
    )
    return {
        "success": True,
        "data": [TaskResponse.model_validate(t).model_dump() for t in tasks],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/{task_id}")
async def get_task(task_id: str, orch: SourcingOrchestrator = Depends(_get_orchestrator)):
    task = await orch.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "data": TaskResponse.model_validate(task).model_dump()}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, orch: SourcingOrchestrator = Depends(_get_orchestrator)):
    ok = await orch.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法取消（已完成/不存在）")
    return {"success": True, "message": "已取消"}


@router.post("/{task_id}/dispatch")
async def dispatch_task(task_id: str, orch: SourcingOrchestrator = Depends(_get_orchestrator)):
    task = await orch.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "pending":
        raise HTTPException(status_code=400, detail=f"当前状态不允许投递: {task.status}")
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        from app.sourcing.config import sourcing_settings
        pool = await create_pool(
            RedisSettings(host="localhost", port=6379, database=sourcing_settings.arq_redis_db)
        )
        await pool.enqueue_job("crawl_task", task_id=task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"投递失败: {e}")
    return {"success": True, "message": "已投递到队列"}


@router.get("/{task_id}/logs")
async def get_task_logs(
    task_id: str,
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """P1-14: 获取任务采集日志"""
    query = select(CrawlLog).where(CrawlLog.task_id == task_id)
    if platform:
        query = query.where(CrawlLog.platform == platform)
    query = query.order_by(CrawlLog.started_at.asc())
    result = await db.execute(query)
    logs = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": log.id,
                "platform": log.platform,
                "status": log.status,
                "candidates_found": log.candidates_found,
                "error_message": log.error_message,
                "duration_seconds": log.duration_seconds,
                "proxy_used": log.proxy_used,
                "captcha_solved": log.captcha_solved,
                "retry_count": log.retry_count,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "finished_at": log.finished_at.isoformat() if log.finished_at else None,
            }
            for log in logs
        ],
        "total": len(logs),
    }
