"""v0.6a: RQ worker entry for parse tasks.

启动:
    rq worker parse_queue -u $REDIS_URL
    或: make celery:watch (双 fork watchdog)

任务实际逻辑在 _do_extract_and_link (v0.5a 抽出)。
RQ 默认跑在 sync 上下文, 用 asyncio.run 包装 async 函数。
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def run_parse_task(raw_resume_id: str, content: str, auto_create: bool = True) -> dict:
    """RQ worker entry — 调 _do_extract_and_link 跑 LLM extract + 状态机更新。

    Returns _do_extract_and_link 返回的 dict, RQ 自动存 result_ttl=3600s。
    """
    from app.tools.resume_parser import _do_extract_and_link

    logger.info("RQ parse task start: raw_resume_id=%s", raw_resume_id)
    result = asyncio.run(
        _do_extract_and_link(raw_resume_id, content, auto_create=auto_create)
    )
    logger.info(
        "RQ parse task done: raw_resume_id=%s status=%s",
        raw_resume_id,
        result.get("status"),
    )
    return result
