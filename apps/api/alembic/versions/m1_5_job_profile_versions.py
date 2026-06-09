"""M1-5: job profile versions and structured items.

Revision ID: m1_5_job_profile_versions
Revises: m1_4_scorecards
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m1_5_job_profile_versions"
down_revision: str | Sequence[str] | None = "m1_4_scorecards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    version_status = postgresql.ENUM("draft", "active", "archived", name="job_profile_version_status")
    requirement_type = postgresql.ENUM("hard", "soft", name="job_profile_requirement_type")
    bind = op.get_bind()
    version_status.create(bind, checkfirst=True)
    requirement_type.create(bind, checkfirst=True)

    op.create_table(
        "job_profile_versions",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("job_profile_id", postgresql.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="job_profile_version_status", create_type=False),
            nullable=False,
        ),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_profile_id"], ["job_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_profile_id", "version", name="uq_job_profile_versions_profile_version"),
    )
    op.create_index("ix_job_profile_versions_job_profile_id", "job_profile_versions", ["job_profile_id"])
    op.create_index("ix_job_profile_versions_status", "job_profile_versions", ["status"])

    op.create_table(
        "job_profile_requirement_items",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("profile_version_id", postgresql.UUID(), nullable=False),
        sa.Column("type", postgresql.ENUM(name="job_profile_requirement_type", create_type=False), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("must_have", sa.Boolean(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("evidence_required", sa.Text(), nullable=True),
        sa.Column("red_flag_if_missing", sa.Boolean(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_version_id"], ["job_profile_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_profile_requirement_items_profile_version_id",
        "job_profile_requirement_items",
        ["profile_version_id"],
    )
    op.create_index("ix_job_profile_requirement_items_type", "job_profile_requirement_items", ["type"])
    op.create_index("ix_job_profile_requirement_items_category", "job_profile_requirement_items", ["category"])

    op.create_table(
        "job_profile_dimensions",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("profile_version_id", postgresql.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("must_have", sa.Text(), nullable=True),
        sa.Column("key_questions", sa.JSON(), nullable=False),
        sa.Column("red_flags", sa.JSON(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_version_id"], ["job_profile_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_profile_dimensions_profile_version_id", "job_profile_dimensions", ["profile_version_id"])
    op.create_index("ix_job_profile_dimensions_name", "job_profile_dimensions", ["name"])

    op.add_column("scorecard_templates", sa.Column("profile_version_id", postgresql.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_scorecard_templates_profile_version_id_job_profile_versions",
        "scorecard_templates",
        "job_profile_versions",
        ["profile_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_scorecard_templates_profile_version_id", "scorecard_templates", ["profile_version_id"])


def downgrade() -> None:
    op.drop_index("ix_scorecard_templates_profile_version_id", table_name="scorecard_templates")
    op.drop_constraint(
        "fk_scorecard_templates_profile_version_id_job_profile_versions",
        "scorecard_templates",
        type_="foreignkey",
    )
    op.drop_column("scorecard_templates", "profile_version_id")
    op.drop_index("ix_job_profile_dimensions_name", table_name="job_profile_dimensions")
    op.drop_index("ix_job_profile_dimensions_profile_version_id", table_name="job_profile_dimensions")
    op.drop_table("job_profile_dimensions")
    op.drop_index("ix_job_profile_requirement_items_category", table_name="job_profile_requirement_items")
    op.drop_index("ix_job_profile_requirement_items_type", table_name="job_profile_requirement_items")
    op.drop_index(
        "ix_job_profile_requirement_items_profile_version_id",
        table_name="job_profile_requirement_items",
    )
    op.drop_table("job_profile_requirement_items")
    op.drop_index("ix_job_profile_versions_status", table_name="job_profile_versions")
    op.drop_index("ix_job_profile_versions_job_profile_id", table_name="job_profile_versions")
    op.drop_table("job_profile_versions")
    bind = op.get_bind()
    postgresql.ENUM(name="job_profile_requirement_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="job_profile_version_status").drop(bind, checkfirst=True)
