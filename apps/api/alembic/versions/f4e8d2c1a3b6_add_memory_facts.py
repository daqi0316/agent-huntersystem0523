"""Add memory_facts table for structured memory layer.

Revision ID: f4e8d2c1a3b6
Revises: 9e3062a04839
Create Date: 2026-05-27 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f4e8d2c1a3b6"
down_revision: Union[str, None] = "9e3062a04839"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("fact_type", sa.String(50), nullable=False,
                  comment="candidate_action | decision | preference | workflow_state | agent_action"),
        sa.Column("subject_type", sa.String(50), nullable=True,
                  comment="candidate | job | application | interview"),
        sa.Column("subject_id", sa.String(255), nullable=True),
        sa.Column("verb", sa.String(50), nullable=False,
                  comment="viewed | screened | scheduled | passed | failed | prefers_* | moved_to | generated_jd | searched | …"),
        sa.Column("object_value", postgresql.JSONB, nullable=True,
                  comment="Structured payload relevant to the verb"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_memory_facts_user_subject",
        "memory_facts",
        ["user_id", "subject_type", "subject_id"],
    )
    op.create_index(
        "idx_memory_facts_user_type",
        "memory_facts",
        ["user_id", "fact_type"],
    )
    op.create_index(
        "idx_memory_facts_user_verb",
        "memory_facts",
        ["user_id", "verb"],
    )


def downgrade() -> None:
    op.drop_index("idx_memory_facts_user_verb", table_name="memory_facts")
    op.drop_index("idx_memory_facts_user_type", table_name="memory_facts")
    op.drop_index("idx_memory_facts_user_subject", table_name="memory_facts")
    op.drop_table("memory_facts")
