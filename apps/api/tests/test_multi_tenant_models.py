"""P5-1 PR 1 单元测试 — 数据模型 + schema 验证。

覆盖:
  - 4 个新 model 可 import
  - 字段类型 + enum 值正确
  - FK 约束正确
  - User 加 is_platform_admin + last_login_at
"""

from app.models import (
    Organization,
    OrganizationPlan,
    OrganizationStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
    Invitation,
    InvitationStatus,
    User,
)


def test_organization_enum_values():
    assert OrganizationPlan.STARTER.value == "starter"
    assert OrganizationPlan.PRO.value == "pro"
    assert OrganizationPlan.ENTERPRISE.value == "enterprise"
    assert OrganizationStatus.ACTIVE.value == "active"
    assert OrganizationStatus.TRIAL.value == "trial"
    assert OrganizationStatus.SUSPENDED.value == "suspended"
    assert OrganizationStatus.DELETED.value == "deleted"


def test_membership_enum_values():
    assert MembershipRole.OWNER.value == "owner"
    assert MembershipRole.HR.value == "hr"
    assert MembershipRole.VIEWER.value == "viewer"
    assert MembershipRole.API.value == "api"
    assert MembershipStatus.ACTIVE.value == "active"
    assert MembershipStatus.PENDING.value == "pending"
    assert MembershipStatus.SUSPENDED.value == "suspended"


def test_invitation_enum_values():
    assert InvitationStatus.PENDING.value == "pending"
    assert InvitationStatus.ACCEPTED.value == "accepted"
    assert InvitationStatus.EXPIRED.value == "expired"
    assert InvitationStatus.CANCELLED.value == "cancelled"


def test_organization_tablename_and_pk():
    assert Organization.__tablename__ == "organization"
    pk_cols = [c.name for c in Organization.__table__.primary_key.columns]
    assert pk_cols == ["id"]


def test_membership_unique_constraint():
    constraints = [
        c.name for c in Membership.__table__.constraints if hasattr(c, "name") and c.name
    ]
    assert "uq_membership_org_user" in constraints


def test_organization_default_quotas():
    assert Organization.__table__.c.quota_max_users.default.arg == 10
    assert Organization.__table__.c.quota_max_candidates.default.arg == 1000
    assert Organization.__table__.c.quota_max_storage_mb.default.arg == 5000
    assert Organization.__table__.c.quota_llm_tokens_per_month.default.arg == 500_000


def test_organization_indexes():
    indexes = {i.name for i in Organization.__table__.indexes}
    assert "ix_organization_slug" in indexes


def test_user_has_platform_admin_field():
    assert hasattr(User, "is_platform_admin")
    assert hasattr(User, "last_login_at")


def test_organization_fk_cascade():
    fk_org_id = next(
        (fk for fk in Invitation.__table__.foreign_keys if fk.column.table.name == "organization"),
        None,
    )
    assert fk_org_id is not None
    assert fk_org_id.ondelete == "CASCADE"


def test_membership_fk_cascade():
    fk_org = next(
        (fk for fk in Membership.__table__.foreign_keys if fk.column.table.name == "organization"),
        None,
    )
    fk_user = next(
        (
            fk for fk in Membership.__table__.foreign_keys
            if fk.column.table.name == "users" and fk.parent.name == "user_id"
        ),
        None,
    )
    fk_inviter = next(
        (
            fk for fk in Membership.__table__.foreign_keys
            if fk.column.table.name == "users" and fk.parent.name == "invited_by"
        ),
        None,
    )
    assert fk_org is not None
    assert fk_org.ondelete == "CASCADE"
    assert fk_user is not None
    assert fk_user.ondelete == "CASCADE"
    assert fk_inviter is not None
    assert fk_inviter.ondelete == "SET NULL"
