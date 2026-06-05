"""P5-1 PR 8 — 老数据迁移。

PR 2 已把所有业务表 org_id 设为 default org UUID (00000000-0000-0000-0000-000000000000)。
本 migration:
  1. 建 default organization (id 匹配)
  2. 所有现有 user → default org owner
  3. 通知现有用户 (站内信)

老用户无感: 他们的数据已挂在 default org, token 仍可用 (PR 7 /auth/me 返回 default org)。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5_1_pr_8_default_org_migration"
down_revision: Union[str, Sequence[str], None] = "p5_1_pr_2_org_id_business"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "Default Organization (迁移中)"


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        f"INSERT INTO organization (id, slug, name, plan, status) "
        f"VALUES ('{DEFAULT_ORG_ID}', '{DEFAULT_ORG_SLUG}', '{DEFAULT_ORG_NAME}', "
        f"'enterprise', 'active') "
        f"ON CONFLICT (id) DO NOTHING"
    )

    op.execute(
        f"INSERT INTO membership (id, org_id, user_id, role, status, joined_at) "
        f"SELECT gen_random_uuid(), '{DEFAULT_ORG_ID}', id, 'owner', 'active', NOW() "
        f"FROM \"users\" "
        f"WHERE NOT EXISTS (SELECT 1 FROM membership m WHERE m.user_id = \"users\".id AND m.org_id = '{DEFAULT_ORG_ID}')"
    )

    rows = bind.execute(
        sa.text(
            "SELECT id, email, name FROM \"users\" "
            "WHERE is_platform_admin = false "
            "LIMIT 1000"
        )
    ).fetchall()
    for user_id, email, name in rows:
        name_str = name if name else "用户"
        input_escaped = (
            f'{{"event":"data_migrated","name":"{name_str}"}}'
        ).replace("'", "''")
        op.execute(
            f"INSERT INTO operation_logs (id, agent_name, action, user_id, input_summary, status) "
            f"VALUES (gen_random_uuid(), 'org_migration', 'notify', '{user_id}', "
            f"'{input_escaped}', 'success')"
        )


def downgrade() -> None:
    op.execute(f"DELETE FROM operation_logs WHERE agent_name = 'org_migration'")
    op.execute(f"DELETE FROM membership WHERE org_id = '{DEFAULT_ORG_ID}'")
    op.execute(f"DELETE FROM organization WHERE id = '{DEFAULT_ORG_ID}'")
