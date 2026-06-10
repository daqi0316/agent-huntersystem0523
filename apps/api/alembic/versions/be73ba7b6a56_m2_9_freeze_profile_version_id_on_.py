"""M2.9: freeze profile_version_id on interview creation

Adds job_profile_id and profile_version_id foreign keys to interviews
so the decision chain (interview -> job profile version) is frozen
at interview creation time.

Revision ID: be73ba7b6a56
Revises: m2_8_weight_and_evidence_constraints
Create Date: 2026-06-09 14:55:58.805439

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "be73ba7b6a56"
down_revision: Union[str, Sequence[str], None] = "m2_8_weight_and_evidence_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add job_profile_id FK (nullable, SET NULL on delete)
    op.add_column(
        "interviews",
        sa.Column("job_profile_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_index(
        op.f("ix_interviews_job_profile_id"),
        "interviews",
        ["job_profile_id"],
        unique=False,
    )
    op.create_foreign_key(
        None,
        "interviews",
        "job_profiles",
        ["job_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add profile_version_id FK (nullable, SET NULL on delete)
    op.add_column(
        "interviews",
        sa.Column(
            "profile_version_id", postgresql.UUID(as_uuid=False), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_interviews_profile_version_id"),
        "interviews",
        ["profile_version_id"],
        unique=False,
    )
    op.create_foreign_key(
        None,
        "interviews",
        "job_profile_versions",
        ["profile_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("interviews_profile_version_id_fkey"), "interviews", type_="foreignkey"
    )
    op.drop_index(op.f("ix_interviews_profile_version_id"), table_name="interviews")
    op.drop_column("interviews", "profile_version_id")
    op.drop_constraint(
        op.f("interviews_job_profile_id_fkey"), "interviews", type_="foreignkey"
    )
    op.drop_index(op.f("ix_interviews_job_profile_id"), table_name="interviews")
    op.drop_column("interviews", "job_profile_id")
