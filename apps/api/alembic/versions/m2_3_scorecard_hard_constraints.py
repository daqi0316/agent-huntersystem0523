"""M2.3: harden scorecard and profile-version constraints.

Revision ID: m2_3_scorecard_hard_constraints
Revises: m2_2_compensation
Create Date: 2026-06-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m2_3_scorecard_hard_constraints"
down_revision: str | Sequence[str] | None = "m2_2_compensation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_scorecard_dimensions_weight_range",
        "scorecard_dimensions",
        "weight > 0 AND weight <= 1",
    )
    op.create_check_constraint(
        "ck_scorecard_behavior_anchors_score_range",
        "scorecard_behavior_anchors",
        "score >= 1 AND score <= 5",
    )
    op.create_unique_constraint(
        "uq_scorecard_behavior_anchors_dimension_score",
        "scorecard_behavior_anchors",
        ["dimension_id", "score"],
    )
    op.create_check_constraint(
        "ck_interview_scorecard_dimension_scores_score_range",
        "interview_scorecard_dimension_scores",
        "score >= 1 AND score <= 5",
    )
    op.create_check_constraint(
        "ck_interview_scorecard_dimension_scores_confidence_range",
        "interview_scorecard_dimension_scores",
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
    )
    op.create_index(
        "uq_job_profile_versions_one_active",
        "job_profile_versions",
        ["job_profile_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_scorecard_templates_one_active_per_profile_round",
        "scorecard_templates",
        ["job_profile_id", "round_type"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND job_profile_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_scorecard_templates_one_active_per_profile_round", table_name="scorecard_templates")
    op.drop_index("uq_job_profile_versions_one_active", table_name="job_profile_versions")
    op.drop_constraint(
        "ck_interview_scorecard_dimension_scores_confidence_range",
        "interview_scorecard_dimension_scores",
        type_="check",
    )
    op.drop_constraint(
        "ck_interview_scorecard_dimension_scores_score_range",
        "interview_scorecard_dimension_scores",
        type_="check",
    )
    op.drop_constraint(
        "uq_scorecard_behavior_anchors_dimension_score",
        "scorecard_behavior_anchors",
        type_="unique",
    )
    op.drop_constraint("ck_scorecard_behavior_anchors_score_range", "scorecard_behavior_anchors", type_="check")
    op.drop_constraint("ck_scorecard_dimensions_weight_range", "scorecard_dimensions", type_="check")
