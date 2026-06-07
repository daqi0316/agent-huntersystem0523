"""v0.6a: RQ-based async parse task service.

Submit:
  enqueue_parse_task(raw_resume_id, content, auto_create=True) -> task_id
  
Worker 调 _do_extract_and_link (v0.5a 抽出), 不在 API 进程跑 LLM。
Poll 优先读 raw_resumes 表 status (source of truth, _do_extract_and_link 写)。

设计选择 (Momus §3 决策点 1): RQ 而非 Celery
  - 项目轻需求, 1 类任务
  - Redis 已有 (Phase Z ship)
  - RQ 部署 1 worker 进程即可
  - vs Celery: 无 broker/result/beat 复杂度
"""
from __future__ import annotations

import logging
from typing import Any

import redis
from rq import Queue

from app.core.config import settings

logger = logging.getLogger(__name__)

QUEUE_NAME = "parse_queue"


def get_redis_client() -> redis.Redis:
    """Get Redis client from settings.redis_url."""
    return redis.from_url(settings.redis_url)


def get_parse_queue() -> Queue:
    """Get the parse_queue (lazy init for connection retry)."""
    return Queue(QUEUE_NAME, connection=get_redis_client())


def enqueue_parse_task(
    raw_resume_id: str,
    content: str,
    auto_create: bool = True,
) -> str:
    """Enqueue parse task to RQ, return job_id (str).

    Args:
        raw_resume_id: raw_resumes.id (already inserted with status=processing)
        content: raw text (already saved to raw_resumes.raw_text)
        auto_create: whether to create candidate on success (v0.5a 公共函数参数)

    Returns:
        RQ job_id (str), 用于 poll 时关联
    
    Raises:
        redis.exceptions.ConnectionError: Redis 不可达 (caller 返 503)
    """
    from app.workers.parse_worker import run_parse_task

    queue = get_parse_queue()
    job = queue.enqueue(
        run_parse_task,
        raw_resume_id=raw_resume_id,
        content=content,
        auto_create=auto_create,
        job_timeout=300,
        result_ttl=3600,
        failure_ttl=3600,
    )
    return job.id


async def poll_parse_task(raw_resume_id: str) -> dict[str, Any] | None:
    """Poll task status by raw_resume_id.

    Returns None if raw_resume not found, else dict with:
      - raw_resume_id, status (processing/parsed/failed),
        candidate_id, error_message, updated_at
    """
    from app.core.database import AsyncSessionLocal
    from app.models.raw_resume import RawResume

    async with AsyncSessionLocal() as db:
        rr = await db.get(RawResume, raw_resume_id)
        if rr is None:
            return None
        return {
            "raw_resume_id": rr.id,
            "status": rr.status.value,
            "candidate_id": rr.candidate_id,
            "error_message": rr.error_message,
            "updated_at": rr.updated_at.isoformat() if rr.updated_at else None,
        }
