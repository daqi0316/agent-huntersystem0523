"""p0_sourcing_tables

Revision ID: 043c3b04ac57
Revises: p2_c_agent_llm_generations
Create Date: 2026-06-11 17:46:02.197660

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "043c3b04ac57"
down_revision: Union[str, Sequence[str], None] = "p2_c_agent_llm_generations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — add sourcing tables + candidate columns."""

    # ── sourcing_platform_configs ──
    op.create_table(
        "sourcing_platform_configs",
        sa.Column("name", sa.String(50), nullable=False, comment="平台标识"),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column(
            "category", sa.String(20), nullable=False,
            comment="job_board/social/code/academic",
        ),
        sa.Column("anti_crawl_level", sa.Integer(), nullable=False, comment="1-5"),
        sa.Column("requires_login", sa.Boolean(), nullable=False),
        sa.Column("rate_limit", sa.Integer(), nullable=False, comment="请求间隔(秒)"),
        sa.Column(
            "daily_quota_per_account", sa.Integer(), nullable=False,
            comment="每账号日配额",
        ),
        sa.Column(
            "config", postgresql.JSON(astext_type=sa.Text()), nullable=False,
            comment="平台特有配置",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("health_status", sa.String(20), nullable=False),
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("name"),
    )

    # ── sourcing_platform_accounts ──
    op.create_table(
        "sourcing_platform_accounts",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False, comment="账号标识"),
        sa.Column(
            "account_type", sa.String(20), nullable=False,
            comment="primary(主号)/backup(备用)/crawl(采集号)",
        ),
        sa.Column(
            "encrypted_cookies", sa.Text(), nullable=True, comment="AES 加密 Cookie",
        ),
        sa.Column("cookie_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False,
            comment="active/banned/limited/expired",
        ),
        sa.Column("daily_used", sa.Integer(), nullable=False, comment="今日已用配额"),
        sa.Column(
            "quota_reset_at", sa.DateTime(timezone=True), nullable=True,
            comment="配额重置时间",
        ),
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False,
            comment="连续失败次数",
        ),
        sa.Column("last_banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["platform"], ["sourcing_platform_configs.name"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sourcing_platform_accounts_platform"),
        "sourcing_platform_accounts", ["platform"], unique=False,
    )

    # ── sourcing_tasks ──
    op.create_table(
        "sourcing_tasks",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("keyword", sa.String(500), nullable=False, comment="搜索关键词"),
        sa.Column(
            "platforms", postgresql.ARRAY(sa.String()), nullable=True,
            comment="目标平台列表",
        ),
        sa.Column(
            "filters", postgresql.JSON(astext_type=sa.Text()), nullable=False,
            comment="筛选条件: 城市/薪资/年限等",
        ),
        sa.Column(
            "status", sa.String(20), nullable=False,
            comment="pending/running/completed/partial/failed/cancelled",
        ),
        sa.Column(
            "progress", postgresql.JSON(astext_type=sa.Text()), nullable=False,
            comment="各平台进度快照",
        ),
        sa.Column("total_found", sa.Integer(), nullable=False),
        sa.Column("after_dedup", sa.Integer(), nullable=False),
        sa.Column("new_this_run", sa.Integer(), nullable=False, comment="本批新增(去重后)"),
        sa.Column("priority", sa.Integer(), nullable=False, comment="优先级 0-100"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sourcing_tasks_org_id"), "sourcing_tasks", ["org_id"], unique=False,
    )
    op.create_index(
        op.f("ix_sourcing_tasks_status"),
        "sourcing_tasks", ["status"], unique=False,
    )

    # ── crawl_logs ──
    op.create_table(
        "crawl_logs",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("task_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False, comment="平台标识"),
        sa.Column("url", sa.Text(), nullable=True, comment="目标 URL"),
        sa.Column("page", sa.Integer(), nullable=False, comment="页码"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("candidates_found", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("proxy_used", sa.String(100), nullable=True, comment="使用的代理"),
        sa.Column(
            "account_id", sa.UUID(as_uuid=False), nullable=True,
            comment="关联平台账号",
        ),
        sa.Column("captcha_solved", sa.Boolean(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, comment="重试次数"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["sourcing_platform_accounts.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["sourcing_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crawl_logs_account_id"),
        "crawl_logs", ["account_id"], unique=False,
    )
    op.create_index(
        op.f("ix_crawl_logs_task_id"), "crawl_logs", ["task_id"], unique=False,
    )

    # ── candidates — 新增 sourcing 扩展字段 ──
    op.add_column(
        "candidates",
        sa.Column(
            "sourcing_task_id", sa.String(64), nullable=True,
            comment="来源采集任务ID",
        ),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "source_platforms", postgresql.ARRAY(sa.String()), nullable=True,
            comment="来源平台列表",
        ),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "source_urls", postgresql.JSON(astext_type=sa.Text()), nullable=True,
            comment="各平台 URL {boss_zhipin: url, ...}",
        ),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "raw_data", postgresql.JSON(astext_type=sa.Text()), nullable=True,
            comment="各平台原始解析数据 {boss_zhipin: {...}}",
        ),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "ai_analysis", postgresql.JSON(astext_type=sa.Text()), nullable=True,
            comment="AI 分析结果缓存",
        ),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "match_scores", postgresql.JSON(astext_type=sa.Text()), nullable=True,
            comment="按岗位匹配分 {job_id: score}",
        ),
    )
    op.add_column(
        "candidates",
        sa.Column("data_quality_score", sa.Float(), nullable=True, comment="数据质量评分 0-1"),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "dedup_fingerprint", sa.String(128), nullable=True,
            comment="去重指纹",
        ),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "last_crawled_at", sa.DateTime(timezone=True), nullable=True,
            comment="上次采集时间",
        ),
    )
    op.create_index(
        op.f("ix_candidates_sourcing_task_id"),
        "candidates", ["sourcing_task_id"], unique=False,
    )
    op.create_index(
        op.f("ix_candidates_dedup_fingerprint"),
        "candidates", ["dedup_fingerprint"], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema — reverse all additions."""
    # candidates — 删除 sourcing 扩展字段 + 索引
    op.drop_index(op.f("ix_candidates_dedup_fingerprint"), table_name="candidates")
    op.drop_index(op.f("ix_candidates_sourcing_task_id"), table_name="candidates")
    op.drop_column("candidates", "last_crawled_at")
    op.drop_column("candidates", "dedup_fingerprint")
    op.drop_column("candidates", "data_quality_score")
    op.drop_column("candidates", "match_scores")
    op.drop_column("candidates", "ai_analysis")
    op.drop_column("candidates", "raw_data")
    op.drop_column("candidates", "source_urls")
    op.drop_column("candidates", "source_platforms")
    op.drop_column("candidates", "sourcing_task_id")

    # crawl_logs
    op.drop_index(op.f("ix_crawl_logs_task_id"), table_name="crawl_logs")
    op.drop_index(op.f("ix_crawl_logs_account_id"), table_name="crawl_logs")
    op.drop_table("crawl_logs")

    # sourcing_tasks
    op.drop_index(op.f("ix_sourcing_tasks_status"), table_name="sourcing_tasks")
    op.drop_index(op.f("ix_sourcing_tasks_org_id"), table_name="sourcing_tasks")
    op.drop_table("sourcing_tasks")

    # sourcing_platform_accounts
    op.drop_index(
        op.f("ix_sourcing_platform_accounts_platform"),
        table_name="sourcing_platform_accounts",
    )
    op.drop_table("sourcing_platform_accounts")

    # sourcing_platform_configs
    op.drop_table("sourcing_platform_configs")
