"""Demo 数据生成 — 简化版: 1 家公司 + 1 用户 + 1 会员, 验证链路。

复杂实体 (JD/候选人/评估) 通过 UI 或 API 真实创建更稳。

用法:
  python3 scripts/seed-demo-data.py
  python3 scripts/seed-demo-data.py --clean
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("seed-demo")

DEMO_ORG_ID = "demo-org-acme-tech"
DEMO_USER_ID = "demo-user-hr-1"
DEMO_USER_EMAIL = "hr@acme-demo.com"
DEMO_USER_PHONE = "13800000001"


async def seed_demo_data(clean: bool = False) -> None:
    from sqlalchemy import delete
    from app.core.database import AsyncSessionLocal
    from app.core.security import hash_password
    from app.models.membership import Membership
    from app.models.organization import Organization
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        if clean:
            log.info("清空 demo 数据...")
            await db.execute(delete(Membership).where(Membership.org_id == DEMO_ORG_ID))
            await db.execute(delete(User).where(User.id == DEMO_USER_ID))
            await db.execute(delete(Organization).where(Organization.id == DEMO_ORG_ID))
            await db.commit()
            log.info("✅ demo 数据已清空")
            return

        log.info("🌱 插入 demo 数据...")

        org = Organization(
            id=DEMO_ORG_ID,
            name="[demo] Acme Tech 演示公司",
            slug="acme-tech-demo",
            plan="pro",
            status="active",
            quota_max_users=50,
            quota_max_candidates=5000,
            quota_max_storage_mb=10240,
            quota_llm_tokens_per_month=10_000_000,
        )
        db.add(org)
        await db.flush()

        user = User(
            id=DEMO_USER_ID,
            email=DEMO_USER_EMAIL,
            phone=DEMO_USER_PHONE,
            name="演示 HR",
            hashed_password=hash_password("demo123456"),
            is_active=True,
        )
        db.add(user)
        await db.flush()

        membership = Membership(
            id=str(uuid.uuid4()),
            org_id=DEMO_ORG_ID,
            user_id=DEMO_USER_ID,
            role="owner",
            status="active",
        )
        db.add(membership)

        await db.commit()
        log.info("✅ demo 数据插入完成")
        log.info("登录: email=%s password=demo123456", DEMO_USER_EMAIL)
        log.info("org_id=%s user_id=%s", DEMO_ORG_ID, DEMO_USER_ID)


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo 数据生成 / 清理")
    parser.add_argument("--clean", action="store_true", help="清空 demo 数据")
    args = parser.parse_args()
    asyncio.run(seed_demo_data(clean=args.clean))


if __name__ == "__main__":
    main()
