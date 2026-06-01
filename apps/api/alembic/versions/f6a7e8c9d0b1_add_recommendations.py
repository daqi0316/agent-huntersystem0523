"""create recommendations table

Revision ID: f6a7e8c9d0b1
Revises: b2a4d6f3e9c8
Create Date: 2026-05-31 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f6a7e8c9d0b1"
down_revision: str | None = "b2a4d6f3e9c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("type", sa.Enum("candidate_job_match", "new_candidate", "new_job", name="recommendation_type"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("job_positions.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("score", sa.Integer, nullable=True, comment="匹配评分 0-100"),
        sa.Column("reason", sa.Text, nullable=True, comment="推荐理由"),
        sa.Column("read", sa.Boolean, default=False),
        sa.Column("dismissed", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("recommendations")
    op.execute("DROP TYPE IF EXISTS recommendation_type")
