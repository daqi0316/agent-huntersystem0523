"""Onboarding 集成测试 — 用真实 DB 全链路验证 CSV 导入 + 健康度 + CHECK 约束。

替代旧 mock 测试 (test_onboarding.py)，覆盖真实 SQL/约束行为。
要求: DB reachable, alembic upgrade head 已跑。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.database import Base
from app.models.onboarding import (
    BatchImportRequest,
    BatchImportStatus,
    CustomerHealthScore,
)
from app.services.onboarding import (
    import_candidates_csv,
    import_jobs_csv,
    compute_health_score,
    _validate_csv_size,
    _validate_email,
    MAX_CSV_BYTES,
)

# 让 Base.metadata 包含所有表
from app.models import *  # noqa: F401, F403


@pytest_asyncio.fixture
async def db():
    """每个 test 独立 engine + session，测试完后 rollback。"""
    engine = create_async_engine(
        settings.database_url, echo=False, pool_size=2,
    )
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
        await session.rollback()
    finally:
        await session.close()
        await engine.dispose()


# ===== CSV 导入 =====


class TestImportCandidatesIntegration:
    """候选人批量导入 — 真实 DB 全链路"""

    async def test_valid_csv_imports_all(self, db):
        org_id = str(uuid.uuid4())
        tag = str(uuid.uuid4())[:8]
        csv_text = f"name,email\n张三,zhang-{tag}@test.com\n李四,li-{tag}@test.com\n"
        _, result = await import_candidates_csv(db, org_id, "u1", csv_text)
        assert result.total == 2
        assert result.imported == 2
        assert result.failed == 0

    async def test_missing_columns_fails_immediately(self, db):
        org_id = str(uuid.uuid4())
        csv_text = "name\n张三\n"  # 缺 email 列
        _, result = await import_candidates_csv(db, org_id, "u1", csv_text)
        assert result.total == 0
        assert result.imported == 0
        assert result.failed == 0  # pre-parse failure, no row-level errors

    async def test_duplicate_email_in_same_batch(self, db):
        org_id = str(uuid.uuid4())
        dup_email = f"dup-{str(uuid.uuid4())[:8]}@test.com"
        csv_text = f"name,email\n张三,{dup_email}\n李四,{dup_email}\n"
        _, result = await import_candidates_csv(db, org_id, "u1", csv_text)
        assert result.total == 2
        assert result.imported == 1
        assert result.failed == 1
        assert "重复" in result.errors[0]["error"]

    async def test_invalid_email_rejected(self, db):
        org_id = str(uuid.uuid4())
        csv_text = "name,email\n张三,not-an-email\n"
        _, result = await import_candidates_csv(db, org_id, "u1", csv_text)
        assert result.total == 1
        assert result.imported == 0
        assert result.failed == 1

    async def test_empty_csv_no_rows(self, db):
        org_id = str(uuid.uuid4())
        csv_text = "name,email\n"
        _, result = await import_candidates_csv(db, org_id, "u1", csv_text)
        assert result.total == 0
        assert result.imported == 0
        assert result.failed == 0

    async def test_file_too_large_raises(self):
        big = "name,email\n" + ("x,x@x.com\n" * 1_200_000)  # ~12 MB > 10 MB
        with pytest.raises(ValueError, match="CSV 文件过大"):
            _validate_csv_size(big)


class TestImportJobsIntegration:
    """职位批量导入 — 真实 DB 全链路"""

    async def test_valid_jobs_import(self, db):
        org_id = str(uuid.uuid4())
        csv_text = "title,department\nPython 工程师,工程\n前端工程师,工程\n"
        _, result = await import_jobs_csv(db, org_id, "u1", csv_text)
        assert result.total == 2
        assert result.imported == 2

    async def test_duplicate_title_in_csv(self, db):
        org_id = str(uuid.uuid4())
        csv_text = "title\nPython 工程师\nPython 工程师\n"
        _, result = await import_jobs_csv(db, org_id, "u1", csv_text)
        assert result.total == 2
        assert result.imported == 1
        assert result.failed == 1


class TestImportHelpers:
    def test_validate_email_valid(self):
        assert _validate_email("a@b.com")

    def test_validate_email_no_at(self):
        assert not _validate_email("notanemail")

    def test_validate_email_no_domain(self):
        assert not _validate_email("a@")

    def test_validate_email_no_tld(self):
        assert not _validate_email("a@b")

    def test_max_csv_bytes_defined(self):
        assert MAX_CSV_BYTES == 10 * 1024 * 1024

    def test_csv_under_limit(self):
        _validate_csv_size("a,b\n1,2\n")  # should not raise


# ===== 健康度 =====


class TestHealthScoreIntegration:
    """健康度算法 — 用真实 DB 验证查询逻辑"""

    async def test_empty_org_returns_score_with_zero_values(self, db):
        org_id = str(uuid.uuid4())
        score = await compute_health_score(db, org_id)
        assert score.org_id == org_id
        assert score.total_score >= 0
        assert score.total_score <= 100
        assert score.risk_level in ("healthy", "at_risk", "high_risk", "unknown")

    async def test_health_score_persists(self, db):
        org_id = str(uuid.uuid4())
        score1 = await compute_health_score(db, org_id)
        score2 = await compute_health_score(db, org_id)
        # 第二次应更新而非新建
        assert score1.id == score2.id
        assert score1.org_id == score2.org_id


# ===== DB CHECK 约束 =====


class TestCheckConstraints:
    """验证 m3_1 迁移新增的 CHECK 约束确实生效"""

    async def test_invalid_risk_level_rejected(self, db):
        """risk_level 只能存 4 个有效值之一。"""
        with pytest.raises(Exception):  # PG 会抛 IntegrityError
            invalid = CustomerHealthScore(
                id=str(uuid.uuid4()),
                org_id=str(uuid.uuid4()),
                risk_level="invalid_label",
            )
            db.add(invalid)
            await db.commit()

    async def test_score_above_100_rejected(self, db):
        with pytest.raises(Exception):
            invalid = CustomerHealthScore(
                id=str(uuid.uuid4()),
                org_id=str(uuid.uuid4()),
                total_score=999.0,
            )
            db.add(invalid)
            await db.commit()

    async def test_score_below_0_rejected(self, db):
        with pytest.raises(Exception):
            invalid = CustomerHealthScore(
                id=str(uuid.uuid4()),
                org_id=str(uuid.uuid4()),
                total_score=-1.0,
            )
            db.add(invalid)
            await db.commit()

    async def test_valid_score_accepted(self, db):
        org_id = str(uuid.uuid4())
        valid = CustomerHealthScore(
            id=str(uuid.uuid4()),
            org_id=org_id,
            login_score=50.0,
            feature_score=50.0,
            support_score=50.0,
            referral_score=50.0,
            total_score=50.0,
            risk_level="healthy",
        )
        db.add(valid)
        await db.commit()
        # 验证可回读
        loaded = await db.get(CustomerHealthScore, valid.id)
        assert loaded is not None
        assert loaded.total_score == 50.0


# ===== API 端点 =====


class TestOnboardingAPI:
    """HTTP API 端点 — 用真实 DB + mock auth"""

    async def test_csv_template_candidate(self, client):
        resp = await client.get("/api/v1/onboarding/csv-template/candidate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "name" in data["required_columns"]

    async def test_csv_template_job(self, client):
        resp = await client.get("/api/v1/onboarding/csv-template/job_position")
        assert resp.status_code == 200

    async def test_health_score_endpoint(self, client):
        resp = await client.get("/api/v1/onboarding/health-score")
        # 应返回 200（可能 0 值，但不可 500）
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_score" in data
        assert "risk_level" in data

    async def test_unknown_template_returns_400(self, client):
        resp = await client.get("/api/v1/onboarding/csv-template/unknown")
        assert resp.status_code == 400


class TestImportAPIIntegration:
    """导入 API — 用真实 DB + CSV 上传"""

    async def test_import_candidates_endpoint(self, client):
        tag = str(uuid.uuid4())[:8]
        csv_content = f"name,email\n张三,int-{tag}@test.com\n".encode("utf-8")
        resp = await client.post(
            "/api/v1/onboarding/import/candidates",
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["imported"] >= 1
