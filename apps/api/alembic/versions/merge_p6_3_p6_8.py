"""Merge p6_3_trial + p6_8_feishu_wecom heads.

Revision ID: merge_p6_3_p6_8
Revises: p6_3_trial, p6_8_feishu_wecom
Create Date: 2026-06-06 19:00:00.000000
"""
from typing import Sequence, Union

revision: str = "merge_p6_3_p6_8"
down_revision: Union[str, Sequence[str], None] = ("p6_3_trial", "p6_8_feishu_wecom")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
