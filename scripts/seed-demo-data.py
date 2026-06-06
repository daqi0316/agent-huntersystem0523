"""Demo 数据生成脚本 — 1 家公司 + 5 JD + 20 候选人 + 10 评估, 供演示 + 测试用。

用法:
  python3 scripts/seed-demo-data.py
  python3 scripts/seed-demo-data.py --clean  # 清空 demo 数据

只插入 demo_ 前缀的标记, 不污染真实数据。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("seed-demo")

DEMO_ORG_ID = "demo-org-acme-tech"
DEMO_USER_ID = "demo-user-hr-1"
DEMO_PREFIX = "demo_"  # 标识 demo 数据, 便于清理

COMPANIES = ["阿里巴巴", "字节跳动", "美团", "腾讯", "京东", "小米", "华为", "百度"]
SKILLS = {
    "frontend": ["React", "Vue", "TypeScript", "Webpack", "Vite", "Tailwind", "Next.js", "Figma"],
    "backend": ["Python", "FastAPI", "PostgreSQL", "Redis", "Kafka", "Docker", "Kubernetes", "Golang"],
    "data": ["SQL", "Python", "Spark", "Hadoop", "Airflow", "ClickHouse", "Tableau", "机器学习"],
    "product": ["Axure", "Figma", "用户研究", "数据分析", "PRD", "OKR", "A/B 测试", "SQL"],
    "sales": ["客户开发", "谈判", "CRM", "Salesforce", "渠道管理", "团队管理", "行业洞察", "英语"],
}
JDS = [
    ("高级前端工程师", "frontend", "北京", 5, "30-50K"),
    ("后端架构师", "backend", "上海", 8, "50-80K"),
    ("数据分析师", "data", "北京", 3, "20-35K"),
    ("产品经理 (增长方向)", "product", "杭州", 4, "25-40K"),
    ("大客户销售经理", "sales", "深圳", 5, "25-40K + 提成"),
]
CANDIDATE_NAMES = [
    "张伟", "李娜", "王强", "刘洋", "陈静", "杨明", "赵丽", "黄磊", "周婷", "吴峰",
    "徐华", "孙杰", "马莉", "朱涛", "胡颖", "林峰", "何刚", "高翔", "罗敏", "梁欢",
]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _gen_phone(idx: int) -> str:
    return f"138{idx:08d}"


async def seed_demo_data(clean: bool = False) -> None:
    from sqlalchemy import delete, select
    from app.core.database import AsyncSessionLocal
    from app.models.application import Application
    from app.models.candidate import Candidate
    from app.models.interview import Interview
    from app.models.interview_evaluation import InterviewEvaluation
    from app.models.job_position import JobPosition
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.membership import Membership

    async with AsyncSessionLocal() as db:
        if clean:
            log.info("清空 demo 数据...")
            for model in (InterviewEvaluation, Interview, Application, Candidate, JobPosition):
                await db.execute(delete(model).where(
                    getattr(model, "org_id", None) == DEMO_ORG_ID
                ))
            await db.execute(delete(Membership).where(Membership.org_id == DEMO_ORG_ID))
            await db.execute(delete(User).where(User.id == DEMO_USER_ID))
            await db.execute(delete(Organization).where(Organization.id == DEMO_ORG_ID))
            await db.commit()
            log.info("✅ demo 数据已清空")
            return

        log.info("🌱 插入 demo 数据...")

        org = Organization(
            id=DEMO_ORG_ID,
            name=f"{DEMO_PREFIX} Acme Tech 演示公司",
            slug="acme-tech-demo",
            plan="pro",
            is_active=True,
        )
        db.add(org)

        user = User(
            id=DEMO_USER_ID,
            email=f"hr@acme-demo.com",
            phone=_gen_phone(10000000),
            name="演示 HR",
            is_active=True,
        )
        db.add(user)

        membership = Membership(
            id=str(uuid.uuid4()),
            org_id=DEMO_ORG_ID,
            user_id=DEMO_USER_ID,
            role="owner",
            status="active",
        )
        db.add(membership)

        for jd_title, jd_track, jd_city, jd_years, jd_salary in JDS:
            jd = JobPosition(
                id=f"{DEMO_PREFIX}jd-{jd_track}",
                org_id=DEMO_ORG_ID,
                title=jd_title,
                description=(
                    f"我们正在招聘 {jd_title} (工作地: {jd_city}, 经验: {jd_years}+ 年, 薪资: {jd_salary})。\n\n"
                    f"关键技能: {', '.join(random.sample(SKILLS[jd_track], 4))}"
                ),
                location=jd_city,
                years_required=jd_years,
                salary_range=jd_salary,
                status="open",
                created_at=_now() - timedelta(days=7),
            )
            db.add(jd)

        for i, name in enumerate(CANDIDATE_NAMES):
            track = random.choice(list(SKILLS.keys()))
            cand = Candidate(
                id=f"{DEMO_PREFIX}cand-{i+1:02d}",
                org_id=DEMO_ORG_ID,
                name=f"{DEMO_PREFIX}{name}",
                email=f"cand{i+1}@example-demo.com",
                phone=_gen_phone(20000000 + i),
                current_company=random.choice(COMPANIES),
                current_title=f"{track}工程师",
                years_experience=random.randint(2, 10),
                skills=random.sample(SKILLS[track], 5),
                resume_text=(
                    f"{name} - {random.choice(COMPANIES)} {track}工程师, "
                    f"{random.randint(2, 10)} 年经验。熟悉 {', '.join(random.sample(SKILLS[track], 5))}。"
                ),
                created_at=_now() - timedelta(days=random.randint(1, 14)),
            )
            db.add(cand)

        for i in range(10):
            cand_id = f"{DEMO_PREFIX}cand-{random.randint(1, 20):02d}"
            jd_id = f"{DEMO_PREFIX}jd-{random.choice(list(SKILLS.keys()))}"
            eval_row = InterviewEvaluation(
                id=f"{DEMO_PREFIX}eval-{i+1:02d}",
                org_id=DEMO_ORG_ID,
                candidate_id=cand_id,
                job_position_id=jd_id,
                evaluator_id=DEMO_USER_ID,
                score=random.randint(60, 95),
                professional=random.randint(3, 5),
                communication=random.randint(3, 5),
                learning=random.randint(3, 5),
                culture_fit=random.randint(3, 5),
                summary=f"{DEMO_PREFIX} 评估: 候选人技术能力扎实, 沟通清晰, 推荐二面。",
                created_at=_now() - timedelta(days=random.randint(1, 7)),
            )
            db.add(eval_row)

        await db.commit()
        log.info("✅ demo 数据插入完成: 1 公司 / 1 用户 / 5 JD / 20 候选人 / 10 评估")
        log.info("登录 (mock 模式): org_id=%s user_id=%s", DEMO_ORG_ID, DEMO_USER_ID)
        log.info("所有数据以 'demo_' 前缀, 跑 'seed-demo-data.py --clean' 可清空")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo 数据生成 / 清理")
    parser.add_argument("--clean", action="store_true", help="清空 demo 数据")
    args = parser.parse_args()
    asyncio.run(seed_demo_data(clean=args.clean))


if __name__ == "__main__":
    main()
