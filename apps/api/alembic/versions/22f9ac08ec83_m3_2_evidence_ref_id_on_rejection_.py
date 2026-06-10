"""m3_2: evidence_ref_id on rejection records

Adds evidence_ref_id FK to candidate_rejection_records so that
rejection events can reference the specific evidence that triggered them.

Revision ID: 22f9ac08ec83
Revises: m3_1_onboarding_check_constraints
Create Date: 2026-06-09 15:51:15.246918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "22f9ac08ec83"
down_revision: Union[str, Sequence[str], None] = "m3_1_onboarding_check_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidate_rejection_records",
        sa.Column("evidence_ref_id", sa.UUID(as_uuid=False), nullable=True),
    )
    op.create_index(
        op.f("ix_candidate_rejection_records_evidence_ref_id"),
        "candidate_rejection_records",
        ["evidence_ref_id"],
        unique=False,
    )
    op.create_foreign_key(
        None,
        "candidate_rejection_records",
        "evidence_refs",
        ["evidence_ref_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("candidate_rejection_records_evidence_ref_id_fkey"),
        "candidate_rejection_records",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_candidate_rejection_records_evidence_ref_id"),
        table_name="candidate_rejection_records",
    )
    op.drop_column("candidate_rejection_records", "evidence_ref_id")
