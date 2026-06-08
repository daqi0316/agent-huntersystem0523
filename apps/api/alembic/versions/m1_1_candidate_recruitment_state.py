"""M1-1: candidate recruitment state machine.

Revision ID: m1_1_candidate_recruitment_state
Revises: p7_1_interview_recordings
Create Date: 2026-06-08 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "m1_1_candidate_recruitment_state"
down_revision: Union[str, Sequence[str], None] = "p7_1_interview_recordings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATE_LABELS = (
    "new_application",
    "screening",
    "screening_passed",
    "screening_rejected",
    "first_interview_pending",
    "first_interview_scheduled",
    "first_interview_feedback_pending",
    "first_interview_passed",
    "first_interview_rejected",
    "second_interview_pending",
    "second_interview_scheduled",
    "second_interview_feedback_pending",
    "second_interview_passed",
    "second_interview_rejected",
    "offer_negotiation",
    "offer_sent",
    "offer_accepted",
    "offer_rejected",
    "onboarding_pending",
    "hired",
    "probation_tracking",
    "probation_passed",
    "probation_rejected",
)


def upgrade() -> None:
    recruitment_state = postgresql.ENUM(
        *STATE_LABELS,
        name="recruitment_candidate_state",
        create_type=False,
    )
    postgresql.ENUM(*STATE_LABELS, name="recruitment_candidate_state").create(
        op.get_bind(), checkfirst=True
    )

    op.add_column(
        "candidates",
        sa.Column(
            "recruitment_state",
            recruitment_state,
            server_default="new_application",
            nullable=False,
        ),
    )
    op.create_index("ix_candidates_recruitment_state", "candidates", ["recruitment_state"])

    op.create_table(
        "candidate_state_history",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(), nullable=False),
        sa.Column("from_state", recruitment_state, nullable=True),
        sa.Column("to_state", recruitment_state, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("operator_id", sa.String(length=255), nullable=False),
        sa.Column("triggered_actions", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_state_history_candidate_id", "candidate_state_history", ["candidate_id"])
    op.create_index("ix_candidate_state_history_to_state", "candidate_state_history", ["to_state"])


def downgrade() -> None:
    op.drop_index("ix_candidate_state_history_to_state", table_name="candidate_state_history")
    op.drop_index("ix_candidate_state_history_candidate_id", table_name="candidate_state_history")
    op.drop_table("candidate_state_history")
    op.drop_index("ix_candidates_recruitment_state", table_name="candidates")
    op.drop_column("candidates", "recruitment_state")
    sa.Enum(name="recruitment_candidate_state").drop(op.get_bind(), checkfirst=True)
