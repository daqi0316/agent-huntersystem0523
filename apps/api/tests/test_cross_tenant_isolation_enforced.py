"""P5-1 补救: 1 个 dedicated DB-level 跨租户隔离 negative test。

覆盖 spec §5.2 场景:
  1. org_A 建 1 个 user + 1 个 candidate
  2. org_B 建 1 个 user + 1 个 candidate
  3. 用 airecruit_app role (非 superuser) 连 DB
  4. SET app.current_org_id = org_A
  5. 查 candidates → 应只返 org_A 的, 不返 org_B
  6. SET app.current_org_id = org_B → 反之

这是 P5-1 阶段缺的关键 evidence: RLS 真的生效。
之前的 22 测试全是纯 Python (model/enum), 跨租户用 curl 端到端间接覆盖。
"""

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


APP_DSN = (
    settings.database_url.replace(
        "postgresql+asyncpg://postgres:postgres@",
        "postgresql+asyncpg://airecruit_app:app_pw@",
        1,
    )
)


@pytest.mark.asyncio
async def test_rls_isolates_candidates_by_org():
    engine = create_async_engine(APP_DSN, echo=False)
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    cand_a = str(uuid.uuid4())
    cand_b = str(uuid.uuid4())
    email_a = f"cand-a-{org_a[:8]}@rls.test"
    email_b = f"cand-b-{org_b[:8]}@rls.test"
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                "INSERT INTO organization (id, slug, name, plan, status) "
                "VALUES ($1, $2, 'RLS Test A', 'starter', 'active')",
                (org_a, f"rls-a-{org_a[:8]}"),
            )
            await conn.exec_driver_sql(
                "INSERT INTO organization (id, slug, name, plan, status) "
                "VALUES ($1, $2, 'RLS Test B', 'starter', 'active')",
                (org_b, f"rls-b-{org_b[:8]}"),
            )
            await conn.exec_driver_sql("SELECT set_config('app.current_org_id', $1, true)", (org_a,))
            await conn.exec_driver_sql(
                "INSERT INTO candidates (id, org_id, name, email, skills, status) "
                "VALUES ($1, $2, 'Cand A', $3, ARRAY['js']::varchar[], 'active')",
                (cand_a, org_a, email_a),
            )
            await conn.exec_driver_sql("SELECT set_config('app.current_org_id', $1, true)", (org_b,))
            await conn.exec_driver_sql(
                "INSERT INTO candidates (id, org_id, name, email, skills, status) "
                "VALUES ($1, $2, 'Cand B', $3, ARRAY['go']::varchar[], 'active')",
                (cand_b, org_b, email_b),
            )

        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT set_config('app.current_org_id', $1, true)", (org_a,))
            r = await conn.exec_driver_sql(
                "SELECT count(*) FROM candidates WHERE id IN ($1, $2)",
                (cand_a, cand_b),
            )
            row = r.first()
            assert row is not None
            assert row[0] == 1, f"org_A should see 1 candidate, got {row[0]}"

        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT set_config('app.current_org_id', $1, true)", (org_b,))
            r = await conn.exec_driver_sql(
                "SELECT count(*) FROM candidates WHERE id IN ($1, $2)",
                (cand_a, cand_b),
            )
            row = r.first()
            assert row is not None
            assert row[0] == 1, f"org_B should see 1 candidate, got {row[0]}"

        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT set_config('app.current_org_id', '00000000-0000-0000-0000-000000000000', true)")
            r = await conn.exec_driver_sql(
                "SELECT count(*) FROM candidates WHERE id IN ($1, $2)",
                (cand_a, cand_b),
            )
            row = r.first()
            assert row is not None
            assert row[0] == 0, f"unknown org should see 0, got {row[0]}"
    finally:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("DELETE FROM candidates WHERE id IN ($1, $2)", (cand_a, cand_b))
            await conn.exec_driver_sql("DELETE FROM organization WHERE id IN ($1, $2)", (org_a, org_b))
        await engine.dispose()
