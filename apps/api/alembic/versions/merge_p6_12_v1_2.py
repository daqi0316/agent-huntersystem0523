"""merge heads: p6_12_csm_task_fix + v1_2_interview_evaluations

Revision ID: merge_p6_12_v1_2
Revises: p6_12_csm_task_fix, v1_2_interview_evaluations
Create Date: 2026-06-07 13:05:00.000000
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "merge_p6_12_v1_2"
down_revision: Union[str, Sequence[str], None] = ("p6_12_csm_task_fix", "v1_2_interview_evaluations")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
