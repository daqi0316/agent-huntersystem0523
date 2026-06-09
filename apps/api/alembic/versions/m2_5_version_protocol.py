"""M2.5: add effective dating to job profile versions.

Adds activated_by, activated_at, archived_at, effective_from, effective_to
to job_profile_versions per Section 5.1 of the recruiting engineering plan.

Revision ID: m2_5_version_protocol
Revises: m2_4_job_position_recruiting_standard_binding
Create Date: 2026-06-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m2_5_version_protocol"
down_revision: str | Sequence[str] | None = "m2_4_job_position_recruiting_standard_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_profile_versions", sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("job_profile_versions", sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True))
    op.add_column("job_profile_versions", sa.Column("activated_by", sa.String(255), nullable=True))
    op.add_column("job_profile_versions", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("job_profile_versions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("job_profile_versions", "archived_at")
    op.drop_column("job_profile_versions", "activated_at")
    op.drop_column("job_profile_versions", "activated_by")
    op.drop_column("job_profile_versions", "effective_to")
    op.drop_column("job_profile_versions", "effective_from")
