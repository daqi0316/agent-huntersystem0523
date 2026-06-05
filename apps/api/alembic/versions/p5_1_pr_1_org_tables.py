"""P5-1 PR 1: add organization, membership, invitation tables

Revision ID: p5_1_pr_1_org_tables
Revises: a8c0e2f3b4d5
Create Date: 2026-06-05 15:10:11.580865
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_1_pr_1_org_tables"
down_revision: Union[str, Sequence[str], None] = "a8c0e2f3b4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "plan",
            sa.Enum("starter", "pro", "enterprise", name="organization_plan"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "trial", "suspended", "deleted", name="organization_status"),
            nullable=False,
        ),
        sa.Column("quota_max_users", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("quota_max_candidates", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("quota_max_storage_mb", sa.Integer(), nullable=False, server_default="5000"),
        sa.Column("quota_llm_tokens_per_month", sa.Integer(), nullable=False, server_default="500000"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscription_renews_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organization_slug", "organization", ["slug"], unique=True)

    op.create_table(
        "invitation",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "hr", "viewer", "api", name="invitation_role"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("invited_by", sa.String(length=36), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "accepted", "expired", "cancelled", name="invitation_status"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invitation_email", "invitation", ["email"], unique=False)
    op.create_index("ix_invitation_org_id", "invitation", ["org_id"], unique=False)
    op.create_index("ix_invitation_token", "invitation", ["token"], unique=True)

    op.create_table(
        "membership",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "hr", "viewer", "api", name="membership_role"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "pending", "suspended", name="membership_status"),
            nullable=False,
        ),
        sa.Column("invited_by", sa.String(length=36), nullable=True),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_index("ix_membership_org_id", "membership", ["org_id"], unique=False)
    op.create_index("ix_membership_user_id", "membership", ["user_id"], unique=False)

    op.add_column(
        "users",
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "is_platform_admin")
    op.drop_index("ix_membership_user_id", table_name="membership")
    op.drop_index("ix_membership_org_id", table_name="membership")
    op.drop_table("membership")
    op.drop_index("ix_invitation_token", table_name="invitation")
    op.drop_index("ix_invitation_org_id", table_name="invitation")
    op.drop_index("ix_invitation_email", table_name="invitation")
    op.drop_table("invitation")
    op.drop_index("ix_organization_slug", table_name="organization")
    op.drop_table("organization")
    op.execute("DROP TYPE IF EXISTS membership_status")
    op.execute("DROP TYPE IF EXISTS membership_role")
    op.execute("DROP TYPE IF EXISTS invitation_status")
    op.execute("DROP TYPE IF EXISTS invitation_role")
    op.execute("DROP TYPE IF EXISTS organization_status")
    op.execute("DROP TYPE IF EXISTS organization_plan")
