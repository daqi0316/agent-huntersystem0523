"""m3_1: onboarding CHECK constraints — 分数 0-100 范围 + risk_level 枚举白名单。

Pre-m3_1: customer_health_score 的分数字段和 risk_level 字段无 DB 层约束，
可插入越界值（如 total_score=999）或非法标签（如 risk_level='unknown' 拼错）。

m3_1:
  - chk_health_score_range: 5 个分数字段均在 [0, 100]
  - chk_health_risk_level: risk_level IN ('healthy', 'at_risk', 'high_risk', 'unknown')
  - ix_batch_import_created: batch_import_request 按 created_at 降序索引

Revision ID: m3_1_onboarding_check_constraints
Revises: be73ba7b6a56
Create Date: 2026-06-09 15:10:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3_1_onboarding_check_constraints"
down_revision: Union[str, Sequence[str], None] = "be73ba7b6a56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === customer_health_score 分数范围 [0, 100] ===
    op.create_check_constraint(
        "chk_health_score_range",
        "customer_health_score",
        "login_score BETWEEN 0 AND 100 "
        "AND feature_score BETWEEN 0 AND 100 "
        "AND support_score BETWEEN 0 AND 100 "
        "AND referral_score BETWEEN 0 AND 100 "
        "AND total_score BETWEEN 0 AND 100",
    )

    # === risk_level 有效值白名单 ===
    op.create_check_constraint(
        "chk_health_risk_level",
        "customer_health_score",
        "risk_level IN ('healthy', 'at_risk', 'high_risk', 'unknown')",
    )

    # === batch_import_request 时间序索引 ===
    op.create_index("ix_batch_import_created", "batch_import_request", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_batch_import_created", table_name="batch_import_request")
    op.drop_constraint("chk_health_risk_level", "customer_health_score", type_="check")
    op.drop_constraint("chk_health_score_range", "customer_health_score", type_="check")
