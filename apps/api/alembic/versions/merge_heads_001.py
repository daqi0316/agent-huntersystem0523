"""merge three migration heads

Revision ID: merge_heads_001
Revises: a1b2c3d4e5f6, f6a7e8c9d0b1, c0a1f3b8e2d4
Create Date: 2026-06-03
"""
from typing import Sequence, Union
from alembic import op

revision: str = "merge_heads_001"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f6", "f6a7e8c9d0b1", "c0a1f3b8e2d4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
