"""M2.8: 权重总和 = 1.0 CHECK + 证据非空约束 + 低/高分必须 confidence.

- ck_scorecard_templates_weight_sum: total_weight 必须为 1.0（±0.001 浮点容差）
- ck_dimension_scores_evidence_not_empty: evidence 不能为空串
- ck_dimension_scores_low_high_confidence: 分数 ≤2 或 =5 时 confidence 不能为 NULL

Revision ID: m2_8_weight_and_evidence_constraints
Revises: m2_7_ai_decision_audits
Create Date: 2026-06-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m2_8_weight_and_evidence_constraints"
down_revision: str | Sequence[str] | None = "m2_7_ai_decision_audits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 权重总和 = 1.0（浮点容差 ±0.001）
    op.create_check_constraint(
        "ck_scorecard_templates_weight_sum",
        "scorecard_templates",
        "ABS(total_weight - 1.0) <= 0.001",
    )
    # 证据非空
    op.create_check_constraint(
        "ck_dimension_scores_evidence_not_empty",
        "interview_scorecard_dimension_scores",
        "TRIM(evidence) <> ''",
    )
    # 低分(≤2)或高分(=5)必须填 confidence
    op.create_check_constraint(
        "ck_dimension_scores_low_high_confidence",
        "interview_scorecard_dimension_scores",
        "(score <= 2 OR score = 5) AND confidence IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_dimension_scores_low_high_confidence",
        "interview_scorecard_dimension_scores",
        type_="check",
    )
    op.drop_constraint(
        "ck_dimension_scores_evidence_not_empty",
        "interview_scorecard_dimension_scores",
        type_="check",
    )
    op.drop_constraint(
        "ck_scorecard_templates_weight_sum",
        "scorecard_templates",
        type_="check",
    )
