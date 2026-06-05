"""P5-1 PR 2: 15 张业务表加 org_id + 索引 (大表 CONCURRENTLY) + RLS

Revision ID: p5_1_pr_2_org_id_business
Revises: p5_1_pr_1_org_tables
Create Date: 2026-06-05 15:30:00.000000

P0-1 修法: policy 用 COALESCE + NULLIF 兜底 default org, 忘 SET LOCAL 不 500
P0-3 修法: 大表 (command_audit_log / operation_logs / conversation_messages / memory_fact) 用 CONCURRENTLY
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_1_pr_2_org_id_business"
down_revision: Union[str, Sequence[str], None] = "p5_1_pr_1_org_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000000"

POLICY_SQL = """
CREATE POLICY org_isolation ON {table}
USING (
  org_id::uuid = COALESCE(
    NULLIF(current_setting('app.current_org_id', true), '')::uuid,
    '{default_org}'::uuid
  )
)
"""

ENABLE_RLS_SQL = [
    "ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
]

# 大表: CREATE INDEX CONCURRENTLY (事务外)
BIG_TABLES = {
    "command_audit_log",
    "operation_logs",
    "conversation_messages",
    "memory_fact",
}

# 全部 15 张业务表
# 注: interview_evaluations 在 DB 中不存在 (model 声明但 migration 漏建) — pre-existing tech debt, 跳过
ALL_BUSINESS_TABLES = [
    "candidates",
    "job_positions",
    "applications",
    "interviews",
    "settings",
    "session_summaries",
    "memory_facts",
    "mcp_servers",
    "conversation_sessions",
    "conversation_messages",
    "recommendations",
    "command_audit_log",
    "approvals",
    "operation_logs",
]


def upgrade() -> None:
    for table in ALL_BUSINESS_TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS org_id VARCHAR(36) "
            f"NOT NULL DEFAULT '{DEFAULT_ORG_ID}'"
        )

    for table in ALL_BUSINESS_TABLES:
        if table in BIG_TABLES:
            op.execute("COMMIT")
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_{table}_org_id ON {table}(org_id)")
        else:
            op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_org_id ON {table}(org_id)")

    for table in ALL_BUSINESS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(POLICY_SQL.format(table=table, default_org=DEFAULT_ORG_ID))


def downgrade() -> None:
    for table in reversed(ALL_BUSINESS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        if table in BIG_TABLES:
            op.execute("COMMIT")
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS ix_{table}_org_id")
        else:
            op.drop_index(f"ix_{table}_org_id", table_name=table)
        op.drop_column(table, "org_id")
