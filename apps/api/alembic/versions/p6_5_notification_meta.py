"""P6-5: 补 notification.meta 字段 (model 有但表没建)。

Revision ID: p6_5_notification_meta
Revises: p6_5_notification
Create Date: 2026-06-06 20:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p6_5_notification_meta"
down_revision: Union[str, Sequence[str], None] = "p6_5_notification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notification",
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )


def downgrade() -> None:
    op.drop_column("notification", "meta")
