"""M2.4: bind job positions to recruiting standards.

Revision ID: m2_4_job_position_recruiting_standard_binding
Revises: m2_3_scorecard_hard_constraints
Create Date: 2026-06-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m2_4_job_position_recruiting_standard_binding"
down_revision: str | Sequence[str] | None = "m2_3_scorecard_hard_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_positions", sa.Column("job_profile_id", postgresql.UUID(), nullable=True))
    op.add_column("job_positions", sa.Column("profile_version_id", postgresql.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_job_positions_job_profile_id_job_profiles",
        "job_positions",
        "job_profiles",
        ["job_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_job_positions_profile_version_id_job_profile_versions",
        "job_positions",
        "job_profile_versions",
        ["profile_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_job_positions_job_profile_id", "job_positions", ["job_profile_id"])
    op.create_index("ix_job_positions_profile_version_id", "job_positions", ["profile_version_id"])


def downgrade() -> None:
    op.drop_index("ix_job_positions_profile_version_id", table_name="job_positions")
    op.drop_index("ix_job_positions_job_profile_id", table_name="job_positions")
    op.drop_constraint("fk_job_positions_profile_version_id_job_profile_versions", "job_positions", type_="foreignkey")
    op.drop_constraint("fk_job_positions_job_profile_id_job_profiles", "job_positions", type_="foreignkey")
    op.drop_column("job_positions", "profile_version_id")
    op.drop_column("job_positions", "job_profile_id")
