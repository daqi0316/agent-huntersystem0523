"""add trace_id column to operation_logs (AgentOps P1-3)

Revision ID: a9b8c7d6e5f4
Revises: 22f9ac08ec83, a8c0e2f3b4d5, b2a4d6f3e9c8, b7c9d3e5f1a8, be73ba7b6a56, f4e8d2c1a3b6, m1_1_candidate_recruitment_state, m1_2_job_profiles, m1_3_rejection_reasons, m1_4_scorecards, m1_5_job_profile_versions, m1_6_rejection_analytics, m2_1_candidate_timeline, m2_2_compensation, m2_3_scorecard_hard_constraints, m2_4_job_position_recruiting_standard_binding, m2_5_version_protocol, m2_6_evidence_refs, m2_7_ai_decision_audits, m2_8_weight_and_evidence_constraints, m3_1_onboarding_check_constraints, m3_3, m3_4_company_knowledge_items, m3_5_interviewer_calibration, m3_6_red_flag_rules, merge_heads_001, merge_p6_12_v1_2, merge_p6_3_p6_8, p5_10_ai_disclosure, p5_11_anti_abuse, p5_15_onboarding, p5_1_pr_1_org_tables, p5_1_pr_2_org_id_business, p5_1_pr_8_default_org_migration, p5_1_remediation_audit_log, p5_2_wechat_oauth, p5_3_payment, p5_4_privacy, p5_9_legal, p6_5_notification, p6_5_notification_meta, p6_6_support, p6_7_12_missing_tables, p6_8_dingtalk, p7_1_interview_recordings, v0_4d_raw_resume
Create Date: 2026-06-10 14:00:00.000000

P1-3: OperationLog ↔ trace_id 关联
- 添加 trace_id 列，允许 NULL（向后兼容存量数据）
- 添加索引加速按 trace_id 查询
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = (
    "22f9ac08ec83",
    "a8c0e2f3b4d5",
    "b2a4d6f3e9c8",
    "b7c9d3e5f1a8",
    "be73ba7b6a56",
    "f4e8d2c1a3b6",
    "m1_1_candidate_recruitment_state",
    "m1_2_job_profiles",
    "m1_3_rejection_reasons",
    "m1_4_scorecards",
    "m1_5_job_profile_versions",
    "m1_6_rejection_analytics",
    "m2_1_candidate_timeline",
    "m2_2_compensation",
    "m2_3_scorecard_hard_constraints",
    "m2_4_job_position_recruiting_standard_binding",
    "m2_5_version_protocol",
    "m2_6_evidence_refs",
    "m2_7_ai_decision_audits",
    "m2_8_weight_and_evidence_constraints",
    "m3_1_onboarding_check_constraints",
    "m3_3",
    "m3_4_company_knowledge_items",
    "m3_5_interviewer_calibration",
    "m3_6_red_flag_rules",
    "merge_heads_001",
    "merge_p6_12_v1_2",
    "merge_p6_3_p6_8",
    "p5_10_ai_disclosure",
    "p5_11_anti_abuse",
    "p5_15_onboarding",
    "p5_1_pr_1_org_tables",
    "p5_1_pr_2_org_id_business",
    "p5_1_pr_8_default_org_migration",
    "p5_1_remediation_audit_log",
    "p5_2_wechat_oauth",
    "p5_3_payment",
    "p5_4_privacy",
    "p5_9_legal",
    "p6_5_notification",
    "p6_5_notification_meta",
    "p6_6_support",
    "p6_7_12_missing_tables",
    "p6_8_dingtalk",
    "p7_1_interview_recordings",
    "v0_4d_raw_resume",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "operation_logs",
        sa.Column("trace_id", sa.String(36), nullable=True, comment="关联的 Langfuse AgentOps trace ID"),
    )
    op.create_index("idx_oplog_trace_id", "operation_logs", ["trace_id"])


def downgrade() -> None:
    op.drop_index("idx_oplog_trace_id", table_name="operation_logs")
    op.drop_column("operation_logs", "trace_id")
