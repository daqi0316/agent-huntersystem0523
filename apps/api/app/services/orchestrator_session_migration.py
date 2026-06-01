"""PR-V.2 — 一次性迁移：扫描 Redis 中残留的 legacy OrchestratorSession。

PR-V.1 后 multi-stage 编排状态由 LangGraph checkpointer 接管，PR-V.4 会删除
OrchestratorSession 类。中间窗口期内可能有 in-flight session 还停在 Redis 里。
本脚本在 lifespan 启动时执行：

1. SCAN `orch:session:*` 键
2. 对每个 session 解析 sub_tasks 数量和 approval_ids
3. 检查 approval_ids 是否已有 graph 索引（`appr:graph_thread:*`）
4. 输出汇总（总数 / 孤儿 / 可恢复 / 不可恢复）
5. 不删除任何键 — 留给 24h TTL 自然过期 或 legacy /resume 处理

不可恢复的 session（无 graph 索引 + approval 仍 pending）会打 WARNING，让
ops 在 PR-V.4 之前人工确认或 kill。
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


_LEGACY_SESSION_PREFIX = "orch:session:"
_GRAPH_THREAD_INDEX_PREFIX = "appr:graph_thread:"


async def migrate_legacy_orchestrator_sessions() -> dict[str, Any]:
    """扫描并汇总 Redis 中残留的 legacy OrchestratorSession。

    Returns:
        {
          "scanned": int,         # 总扫描数
          "with_approvals": int,  # 有 approval_ids 的 session 数
          "resumable_via_graph": int,  # 至少一个 approval 有 graph 索引
          "orphaned": int,        # 完全无 graph 索引的 session 数
          "session_ids": list[str],
        }
    """
    summary = {
        "scanned": 0,
        "with_approvals": 0,
        "resumable_via_graph": 0,
        "orphaned": 0,
        "session_ids": [],
    }

    from app.core.redis import get_redis

    try:
        client = await get_redis()
    except Exception as e:
        logger.warning("Migration skipped — Redis unavailable: %s", e)
        return summary

    if client is None:
        logger.info("Migration skipped — no Redis client")
        return summary

    try:
        keys = await _scan_keys(client, _LEGACY_SESSION_PREFIX)
    except Exception as e:
        logger.warning("Migration SCAN failed: %s", e)
        return summary

    for key in keys:
        summary["scanned"] += 1
        session_id = key.decode() if isinstance(key, bytes) else key
        session_id = session_id[len(_LEGACY_SESSION_PREFIX):]
        summary["session_ids"].append(session_id)

        try:
            raw = await client.get(key)
        except Exception as e:
            logger.warning("Failed to read %s: %s", key, e)
            continue

        if raw is None:
            continue

        try:
            data = json.loads(raw)
        except Exception as e:
            logger.warning("Failed to parse session %s: %s", session_id, e)
            continue

        approval_ids = data.get("approval_ids") or []
        if not approval_ids:
            continue

        summary["with_approvals"] += 1

        has_graph_index = False
        for aid in approval_ids:
            index_key = _GRAPH_THREAD_INDEX_PREFIX + aid
            try:
                if await client.exists(index_key):
                    has_graph_index = True
                    break
            except Exception:
                continue

        if has_graph_index:
            summary["resumable_via_graph"] += 1
        else:
            summary["orphaned"] += 1
            logger.warning(
                "Orphaned legacy session %s — %d approval(s) without graph index: %s",
                session_id, len(approval_ids), approval_ids,
            )

    if summary["scanned"] > 0:
        logger.info(
            "Legacy OrchestratorSession migration: scanned=%d with_approvals=%d "
            "resumable_via_graph=%d orphaned=%d",
            summary["scanned"], summary["with_approvals"],
            summary["resumable_via_graph"], summary["orphaned"],
        )
    else:
        logger.info("Legacy OrchestratorSession migration: no legacy sessions found")

    return summary


async def _scan_keys(client: Any, pattern: str) -> list[Any]:
    """SCAN a Redis keyspace — non-blocking, paginates internally."""
    keys: list[Any] = []
    cursor = 0
    try:
        cursor, batch = await client.scan(cursor=cursor, match=pattern + "*", count=200)
        keys.extend(batch or [])
        while cursor:
            cursor, batch = await client.scan(cursor=cursor, match=pattern + "*", count=200)
            keys.extend(batch or [])
            if cursor == 0:
                break
    except AttributeError:
        keys = await client.keys(pattern + "*")
    return keys
