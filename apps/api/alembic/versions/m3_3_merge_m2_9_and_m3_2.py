"""m3_3: 合入 m2_9 与 m3_2_recruiting_intelligence 两条分支。

Branch A: m3_1_onboarding_check_constraints → 22f9ac08ec83 → m2_9
Branch B: m3_1_onboarding_check_constraints → m3_2_recruiting_intelligence

Revision ID: m3_3
Revises: m2_9, m3_2_recruiting_intelligence
Create Date: 2026-06-09 16:15:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "m3_3"
down_revision: Union[str, Sequence[str], None] = ("m2_9", "m3_2_recruiting_intelligence")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
