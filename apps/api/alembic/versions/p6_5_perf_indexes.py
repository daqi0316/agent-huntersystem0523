"""P6-5: 性能优化 — 缺失索引 / GIN / 组合索引。

1. candidates.skills (ARRAY String) — GIN 索引（支持 skills.any() 查询）
2. candidates.raw_data (JSON) — GIN 索引（支持 JSON 路径查询）
3. candidates(org_id, status) — 组合索引（列表页过滤）
4. crawl_logs(task_id, platform) — 组合索引（任务日志按平台筛选）
5. sourcing_tasks(org_id, status) — 组合索引（任务列表过滤）

Revision ID: p6_5_perf_indexes
Revises: p6_4_candidates_archive
Create Date: 2026-06-11 22:15:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "p6_5_perf_indexes"
down_revision: Union[str, Sequence[str], None] = "p6_4_candidates_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. candidates.skills — GIN (ARRAY) ──
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_skills_gin ON candidates USING GIN (skills)")

    # ── 2. candidates.raw_data — GIN (JSONB) ──
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_raw_data_gin ON candidates USING GIN (raw_data)")

    # ── 3. candidates(org_id, status) — 组合索引 ──
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_candidates_org_status ON candidates (org_id, status)"
    )

    # ── 4. crawl_logs(task_id, platform) — 组合索引 ──
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crawl_logs_task_platform ON crawl_logs (task_id, platform)"
    )

    # ── 5. sourcing_tasks(org_id, status) — 组合索引 ──
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sourcing_tasks_org_status ON sourcing_tasks (org_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_candidates_skills_gin")
    op.execute("DROP INDEX IF EXISTS ix_candidates_raw_data_gin")
    op.execute("DROP INDEX IF EXISTS ix_candidates_org_status")
    op.execute("DROP INDEX IF EXISTS ix_crawl_logs_task_platform")
    op.execute("DROP INDEX IF EXISTS ix_sourcing_tasks_org_status")
