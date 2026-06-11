#!/usr/bin/env python3
"""
P6-4: 候选人数据归档脚本 (180天冷数据)

将 candidates 表中超过 180 天未更新的终端状态候选人移至 candidates_archive。
终端状态: completed, failed, blacklisted, archived

用法:
  python scripts/archive_candidates.py                      # 默认 180 天
  python scripts/archive_candidates.py --dry-run            # 仅预览，不操作
  python scripts/archive_candidates.py --days 90            # 自定义天数
  python scripts/archive_candidates.py --batch 100          # 每批 100 条
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

# ── 让 Python 能找到 apps/api ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

import asyncio
import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


# 终端状态: 不会再变更的候选人
TERMINAL_STATUSES = frozenset({"completed", "failed", "blacklisted", "archived"})

# 从 candidates SELECT 的列（与 candidates_archive 结构一致）
ARCHIVE_COLUMNS = [
    "id", "org_id", "name", "email", "phone", "summary", "skills",
    "experience_years", "education", "current_company", "current_title",
    "status", "recruitment_state", "sourcing_task_id", "source_platforms",
    "source_urls", "raw_data", "ai_analysis", "match_scores",
    "data_quality_score", "dedup_fingerprint", "last_crawled_at",
    "created_at", "updated_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive stale candidates to candidates_archive")
    parser.add_argument("--days", type=int, default=180, help="Archive candidates with updated_at older than N days (default: 180)")
    parser.add_argument("--batch", type=int, default=500, help="Batch size per transaction (default: 500)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be archived, don't execute")
    parser.add_argument("--db-url", default=None, help="Database URL (default: from env DATABASE_URL or config)")
    return parser.parse_args()


def get_db_url() -> str:
    """获取数据库 URL，优先级: CLI 参数 > 环境变量 > 硬编码 fallback。"""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # 尝试从 apps/api/.env 读取
    env_path = os.path.join(
        os.path.dirname(__file__), "..", "apps", "api", ".env"
    )
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    # 从 app.core.config 读取（需要 uv venv 激活）
    try:
        from app.core.config import settings
        return settings.database_url
    except ImportError:
        pass
    raise RuntimeError(
        "Cannot determine DATABASE_URL. Set env DATABASE_URL or run from project root after 'source .venv/bin/activate'."
    )


async def archivable_candidates(
    session: AsyncSession, cutoff: datetime, batch: int
) -> list[dict[str, Any]]:
    """查询可归档的候选人列表。"""
    status_list = list(TERMINAL_STATUSES)
    result = await session.execute(
        text("""
            SELECT {cols}
            FROM candidates
            WHERE status = ANY(:statuses)
              AND updated_at < :cutoff
            ORDER BY updated_at ASC
            LIMIT :batch
        """.format(cols=", ".join(ARCHIVE_COLUMNS))),
        {
            "statuses": status_list,
            "cutoff": cutoff,
            "batch": batch,
        },
    )
    rows = result.mappings().all()
    return [dict(row) for row in rows]


async def insert_archive(session: AsyncSession, rows: list[dict[str, Any]], reason: str) -> int:
    """批量插入到 candidates_archive。"""
    if not rows:
        return 0
    now = datetime.now(timezone.utc)
    values = []
    for r in rows:
        values.append({
            **r,
            "archived_at": now,
            "archive_reason": reason,
        })
    # 逐行 INSERT ... ON CONFLICT DO NOTHING （防 email 唯一冲突导致的重复归档）
    count = 0
    for v in values:
        cols = list(v.keys())
        placeholders = [f":{c}" for c in cols]
        await session.execute(
            text(
                "INSERT INTO candidates_archive ({cols}) VALUES ({placeholders}) ON CONFLICT (email) DO NOTHING".format(
                    cols=", ".join(cols),
                    placeholders=", ".join(placeholders),
                )
            ),
            v,
        )
        count += 1
    await session.commit()
    return count


async def delete_archived(session: AsyncSession, ids: list[str]) -> int:
    """从 candidates 删除已归档记录（CASCADE 清理关联表）。"""
    result = await session.execute(
        text("DELETE FROM candidates WHERE id = ANY(:ids)"),
        {"ids": ids},
    )
    await session.commit()
    return result.rowcount


async def main():
    args = parse_args()
    db_url = get_db_url()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    # asyncpg 需要 postgresql+asyncpg:// 或 postgresql://
    if db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, pool_pre_ping=True, pool_size=2)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    total_archived = 0
    total_deleted = 0

    while True:
        async with async_session() as session:
            rows = await archivable_candidates(session, cutoff, args.batch)

        if not rows:
            break

        ids = [r["id"] for r in rows]

        if args.dry_run:
            print(f"[DRY-RUN] Would archive {len(rows)} candidates (IDs: {ids[0]}..{ids[-1]})")
            total_archived += len(rows)
            async with async_session() as session:
                await session.rollback()
        else:
            async with async_session() as session:
                inserted = await insert_archive(session, rows, "180d_auto")
                print(f"  Inserted {inserted} into candidates_archive")
            async with async_session() as session:
                deleted = await delete_archived(session, ids)
                print(f"  Deleted {deleted} from candidates (CASCADE cleaned related records)")
            total_archived += inserted
            total_deleted += deleted

        if len(rows) < args.batch:
            break

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Done. "
          f"Archived: {total_archived}, Deleted: {total_deleted}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
