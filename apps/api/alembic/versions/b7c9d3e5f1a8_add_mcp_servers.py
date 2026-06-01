"""Add mcp_servers table for MCP server configuration.

Revision ID: b7c9d3e5f1a8
Revises: f4e8d2c1a3b6
Create Date: 2026-05-27 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7c9d3e5f1a8"
down_revision: Union[str, None] = "f4e8d2c1a3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False,
                  comment="用户自定义名称"),
        sa.Column("server_url", sa.String(1024), nullable=False,
                  comment="MCP server HTTP endpoint"),
        sa.Column("protocol", sa.String(32), nullable=False, server_default="streamable-http",
                  comment="传输协议: streamable-http | sse"),
        sa.Column("auth_type", sa.String(32), nullable=False, server_default="none",
                  comment="认证方式: none | bearer | basic"),
        sa.Column("auth_token", sa.Text, nullable=True,
                  comment="凭证"),
        sa.Column("tools_cache", sa.Text, nullable=True,
                  comment="缓存的工具列表 JSON"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true(),
                  comment="是否启用"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("mcp_servers")
