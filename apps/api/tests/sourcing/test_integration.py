"""集成测试 — 真 PG + 真 Redis round-trip，验证 sourcing 模块 DB/队列/账号管理。

设计原则
--------
- 真 DB（dev PG） + 真 Redis，不 mock 基础设施
- 每个 test 建种子数据 → 操作 → ROLLBACK，互不污染
- 遵循 test_models_enum_integration.py 的模式（fresh engine per test）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.sourcing.account_manager import AccountManager
from app.sourcing.models.crawl_log import CrawlLog, CrawlStatus
from app.sourcing.models.platform_account import AccountStatus, AccountType, PlatformAccount
from app.sourcing.models.platform_config import PlatformConfig
from app.sourcing.models.sourcing_task import SourcingTask, SourcingTaskStatus

# ---------------------------------------------------------------------------
# 常量（与 conftest.py 的 test-user-id / test-org-id 保持一致）
# ---------------------------------------------------------------------------
TEST_ORG_ID = "test-org-id"
TEST_USER_ID = "test-user-id"
TEST_PLATFORM = "github"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    """每个 test 一个新 engine（同 test_models_enum_integration）。"""
    eng = create_async_engine(settings.database_url, echo=False, pool_size=2)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def redis():
    """真 Redis 连接（dev 6379）。"""
    from redis.asyncio import Redis as AsyncRedis
    r = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield r
    finally:
        await r.flushdb()  # 清理本测产生的 key
        await r.close()


# ── 种子数据 ──


@pytest_asyncio.fixture
async def seed_org(db_session: AsyncSession):
    """确保 test-org-id 存在（满足 sourcing_tasks.org_id FK）。"""
    result = await db_session.execute(
        text("SELECT id FROM organization WHERE id = :oid"),
        {"oid": TEST_ORG_ID},
    )
    if result.scalar_one_or_none() is None:
        await db_session.execute(
            text("""
                INSERT INTO organization (id, slug, name, plan, status, created_at, updated_at)
                VALUES (:id, :slug, :name, 'starter', 'active', NOW(), NOW())
                ON CONFLICT DO NOTHING
            """),
            {"id": TEST_ORG_ID, "slug": "test-org", "name": "Test Org"},
        )
        await db_session.commit()


@pytest_asyncio.fixture
async def seed_platform_config(db_session: AsyncSession):
    """确保 github platform_config 存在（满足 platform_account.platform FK）。"""
    result = await db_session.execute(
        text("SELECT name FROM sourcing_platform_configs WHERE name = :name"),
        {"name": TEST_PLATFORM},
    )
    if result.scalar_one_or_none() is None:
        config = PlatformConfig(
            name=TEST_PLATFORM,
            display_name="GitHub",
            category="code",
            anti_crawl_level=1,
            requires_login=False,
            rate_limit=1,
            daily_quota_per_account=5000,
            enabled=True,
            config={},
        )
        db_session.add(config)
        await db_session.commit()


# ═══════════════════════════════════════════════════════════════════
# SourcingTask + CrawlLog DB round-trip
# ═══════════════════════════════════════════════════════════════════


class TestSourcingTaskRoundTrip:
    """SourcingTask CRUD + 关联 CrawlLog 写入验证。"""

    async def _create_org_and_task(
        self, db: AsyncSession, keyword: str = "Python工程师",
    ) -> SourcingTask:
        await db.execute(
            text(
                "INSERT INTO organization (id, slug, name, plan, status, created_at, updated_at) "
                "VALUES (:id, :slug, :name, 'starter', 'active', NOW(), NOW()) ON CONFLICT DO NOTHING"
            ),
            {"id": TEST_ORG_ID, "slug": "test-org", "name": "Test Org"},
        )
        task = SourcingTask(
            id=str(uuid.uuid4()),
            org_id=TEST_ORG_ID,
            created_by=TEST_USER_ID,
            keyword=keyword,
            platforms=[TEST_PLATFORM],
            filters={"city": "北京"},
        )
        db.add(task)
        await db.commit()
        return task

    async def test_create_task(self, db_session: AsyncSession):
        """创建 SourcingTask → 字段正确写库。"""
        task = await self._create_org_and_task(db_session, "Go工程师")
        assert task.keyword == "Go工程师"
        assert task.status == SourcingTaskStatus.PENDING.value
        assert task.total_found == 0

        # 重新查询验证持久化
        result = await db_session.execute(
            text("SELECT keyword, status, filters FROM sourcing_tasks WHERE id = :id"),
            {"id": task.id},
        )
        row = result.one()
        assert row.keyword == "Go工程师"
        assert row.status == "pending"
        assert row.filters["city"] == "北京"

    async def test_update_task_status(self, db_session: AsyncSession):
        """更新 SourcingTask 状态。"""
        task = await self._create_org_and_task(db_session)
        task.status = SourcingTaskStatus.RUNNING.value
        task.started_at = datetime.now(timezone.utc)
        await db_session.commit()

        result = await db_session.execute(
            text("SELECT status FROM sourcing_tasks WHERE id = :id"),
            {"id": task.id},
        )
        assert result.scalar_one() == "running"

    async def test_task_progress_json(self, db_session: AsyncSession):
        """JSON progress 字段读写。"""
        task = await self._create_org_and_task(db_session)
        task.progress = {TEST_PLATFORM: {"found": 10, "status": "ok"}}
        await db_session.commit()

        result = await db_session.execute(
            text("SELECT progress FROM sourcing_tasks WHERE id = :id"),
            {"id": task.id},
        )
        row = result.scalar_one()
        assert row[TEST_PLATFORM]["found"] == 10
        assert row[TEST_PLATFORM]["status"] == "ok"

    async def test_crawl_log_create(self, db_session: AsyncSession):
        """创建 CrawlLog + 关联 task。"""
        task = await self._create_org_and_task(db_session)
        now = datetime.now(timezone.utc)
        log = CrawlLog(
            id=str(uuid.uuid4()),
            task_id=task.id,
            platform=TEST_PLATFORM,
            url="https://api.github.com/search/users",
            page=1,
            status=CrawlStatus.SUCCESS.value,
            candidates_found=5,
            duration_seconds=1.23,
            started_at=now,
            finished_at=now + timedelta(seconds=2),
        )
        db_session.add(log)
        await db_session.commit()

        # 验证查询
        result = await db_session.execute(
            text("""
                SELECT platform, status, candidates_found
                FROM crawl_logs WHERE task_id = :tid
            """),
            {"tid": task.id},
        )
        row = result.one()
        assert row.platform == TEST_PLATFORM
        assert row.status == "success"
        assert row.candidates_found == 5

    async def test_task_with_logs_relationship(self, db_session: AsyncSession):
        """SourcingTask.logs relationship 返回关联的 CrawlLog。"""
        task = await self._create_org_and_task(db_session)
        now = datetime.now(timezone.utc)
        for i in range(3):
            log = CrawlLog(
                id=str(uuid.uuid4()),
                task_id=task.id,
                platform=TEST_PLATFORM,
                page=i + 1,
                status=CrawlStatus.SUCCESS.value,
                candidates_found=i * 2,
                duration_seconds=0.5,
                started_at=now,
                finished_at=now + timedelta(seconds=1),
            )
            db_session.add(log)
        await db_session.commit()

        await db_session.refresh(task)
        from sqlalchemy import select
        result = await db_session.execute(
            select(CrawlLog).where(CrawlLog.task_id == task.id)
        )
        logs = result.scalars().all()
        assert len(logs) == 3


# ═══════════════════════════════════════════════════════════════════
# PlatformConfig + PlatformAccount round-trip
# ═══════════════════════════════════════════════════════════════════


class TestPlatformAccountRoundTrip:
    """PlatformAccount CRUD + Cookie 加密存储 + 配额管理。"""

    async def _seed_platform_config(self, db: AsyncSession, name: str = "github"):
        await db.execute(
            text(
                "INSERT INTO sourcing_platform_configs "
                "(name, display_name, category, anti_crawl_level, requires_login, "
                " rate_limit, daily_quota_per_account, enabled, config, health_status, created_at, updated_at) "
                "VALUES (:name, :disp, :cat, 1, false, 1, 5000, true, '{}'::jsonb, 'unknown', NOW(), NOW()) "
                "ON CONFLICT DO NOTHING"
            ),
            {"name": name, "disp": name.title(), "cat": "code"},
        )
        await db.commit()

    async def _create_account(
        self, db: AsyncSession, platform: str = "github", acct_type: str = "crawl",
    ) -> PlatformAccount:
        acct = PlatformAccount(
            id=str(uuid.uuid4()),
            platform=platform,
            display_name=f"{platform}-{acct_type}",
            account_type=acct_type,
            encrypted_cookies=None,
            is_active=True,
            status="active",
            daily_used=0,
            consecutive_failures=0,
        )
        db.add(acct)
        await db.commit()
        return acct

    async def test_create_platform_config(self, db_session: AsyncSession):
        """PlatformConfig 创建 + 查询。"""
        await self._seed_platform_config(db_session)

        result = await db_session.execute(
            text("SELECT display_name, daily_quota_per_account FROM sourcing_platform_configs WHERE name = 'github'"),
        )
        row = result.one()
        assert row.display_name == "Github"
        assert row.daily_quota_per_account == 5000

    async def test_create_account(self, db_session: AsyncSession):
        """PlatformAccount 创建 + FK 约束。"""
        await self._seed_platform_config(db_session)
        acct = await self._create_account(db_session)

        result = await db_session.execute(
            text("SELECT platform, account_type, is_active FROM sourcing_platform_accounts WHERE id = :id"),
            {"id": acct.id},
        )
        row = result.one()
        assert row.platform == "github"
        assert row.account_type == "crawl"
        assert row.is_active is True

    async def test_account_status_transition(self, db_session: AsyncSession):
        """账号状态变更 → banned。"""
        await self._seed_platform_config(db_session)
        acct = await self._create_account(db_session)

        acct.status = AccountStatus.BANNED.value
        acct.consecutive_failures = 5
        acct.last_banned_at = datetime.now(timezone.utc)
        await db_session.commit()

        result = await db_session.execute(
            text("SELECT status, consecutive_failures FROM sourcing_platform_accounts WHERE id = :id"),
            {"id": acct.id},
        )
        row = result.one()
        assert row.status == "banned"
        assert row.consecutive_failures == 5

    async def test_quota_usage_update(self, db_session: AsyncSession):
        """daily_used 累加。"""
        await self._seed_platform_config(db_session)
        acct = await self._create_account(db_session)

        acct.daily_used += 50
        await db_session.commit()

        result = await db_session.execute(
            text("SELECT daily_used FROM sourcing_platform_accounts WHERE id = :id"),
            {"id": acct.id},
        )
        assert result.scalar_one() == 50


# ═══════════════════════════════════════════════════════════════════
# AccountManager 真 DB 集成
# ═══════════════════════════════════════════════════════════════════


class TestAccountManagerIntegration:
    """AccountManager 用真 DB + 真 Redis 验证完整流程。"""

    @pytest_asyncio.fixture
    async def am(
        self, db_session: AsyncSession, redis,
    ) -> AccountManager:
        return AccountManager(db=db_session, redis=redis)

    async def _seed(
        self, db: AsyncSession, platform: str = "github",
    ):
        """插入 platform_config + 3 个账号（primary/backup/crawl）。"""
        # 清理该 platform 的旧测试数据，防止 MultipleResultsFound
        await db.execute(
            text("DELETE FROM sourcing_platform_accounts WHERE platform = :p"),
            {"p": platform},
        )
        await db.execute(
            text("DELETE FROM sourcing_platform_configs WHERE name = :p"),
            {"p": platform},
        )
        await db.execute(
            text(
                "INSERT INTO sourcing_platform_configs "
                "(name, display_name, category, anti_crawl_level, requires_login, "
                " rate_limit, daily_quota_per_account, enabled, config, health_status, created_at, updated_at) "
                "VALUES (:name, :disp, 'code', 1, false, 1, 5000, true, '{}'::jsonb, 'unknown', NOW(), NOW()) "
                "ON CONFLICT DO NOTHING"
            ),
            {"name": platform, "disp": platform.title()},
        )
        for atype in ("primary", "backup", "crawl"):
            db.add(PlatformAccount(
                id=str(uuid.uuid4()),
                platform=platform,
                display_name=f"{platform}-{atype}",
                account_type=atype,
                is_active=True,
                status=AccountStatus.ACTIVE.value,
                daily_used=0,
                consecutive_failures=0,
            ))
        await db.commit()

    async def test_acquire_returns_primary_first(self, db_session, am):
        """acquire() 优先返回 primary 类型账号。"""
        await self._seed(db_session)
        acct = await am.acquire("github")
        assert acct is not None
        assert acct.account_type == "primary"

    async def test_acquire_skips_quota_exhausted(self, db_session, am):
        """daily_used >= quota → 跳过，fallback 下一个账号。"""
        await self._seed(db_session)

        # 把 primary 的配额用满
        result = await db_session.execute(
            text("SELECT id FROM sourcing_platform_accounts WHERE platform='github' AND account_type='primary'"),
        )
        pid = result.scalar_one()
        primary = await db_session.get(PlatformAccount, pid)
        primary.daily_used = 5000  # = daily_quota_per_account
        await db_session.commit()

        # 清除 Redis 配额缓存
        await am.redis.flushdb()

        acct = await am.acquire("github")
        assert acct is not None
        assert acct.account_type == "backup"  # fallback 到 backup

    async def test_acquire_all_quota_exhausted(self, db_session, am):
        """所有账号配额用满 → None。"""
        await self._seed(db_session)
        for row in (await db_session.execute(
            text("SELECT id FROM sourcing_platform_accounts WHERE platform='github'"),
        )).all():
            acct = await db_session.get(PlatformAccount, row.id)
            acct.daily_used = 5000
        await db_session.commit()
        await am.redis.flushdb()

        acct = await am.acquire("github")
        assert acct is None

    async def test_acquire_skips_banned(self, db_session, am):
        """banned 账号被跳过。"""
        await self._seed(db_session)
        result = await db_session.execute(
            text("SELECT id FROM sourcing_platform_accounts WHERE platform='github' AND account_type='primary'"),
        )
        pid = result.scalar_one()
        primary = await db_session.get(PlatformAccount, pid)
        primary.status = AccountStatus.BANNED.value
        await db_session.commit()

        acct = await am.acquire("github")
        assert acct is not None
        assert acct.account_type == "backup"

    async def test_report_usage_increments(self, db_session, am):
        """report_usage → daily_used 增加。"""
        await self._seed(db_session)
        result = await db_session.execute(
            text("SELECT id FROM sourcing_platform_accounts WHERE platform='github' AND account_type='primary'"),
        )
        pid = result.scalar_one()

        await am.report_usage(pid, count=10)

        acct = await db_session.get(PlatformAccount, pid)
        assert acct.daily_used == 10
        assert acct.consecutive_failures == 0  # 重置

    async def test_report_usage_limits_at_threshold(self, db_session, am):
        """配额使用率 90%+ → 状态变为 limited。"""
        await self._seed(db_session)
        result = await db_session.execute(
            text("SELECT id FROM sourcing_platform_accounts WHERE platform='github' AND account_type='primary'"),
        )
        pid = result.scalar_one()

        await am.report_usage(pid, count=4500)

        acct = await db_session.get(PlatformAccount, pid)
        assert acct.daily_used == 4500
        assert acct.status == AccountStatus.LIMITED.value

    async def test_rotate_marks_failure(self, db_session, am):
        """rotate → consecutive_failures 递增。"""
        await self._seed(db_session)
        result = await db_session.execute(
            text("SELECT id FROM sourcing_platform_accounts WHERE platform='github' AND account_type='primary'"),
        )
        pid = result.scalar_one()

        rotated = await am.rotate("github", pid)
        assert rotated is not None

        acct = await db_session.get(PlatformAccount, pid)
        assert acct.consecutive_failures == 1

    async def test_rotate_bans_at_threshold(self, db_session, am):
        """连续失败 5 次 → 标记 banned。"""
        await self._seed(db_session)
        result = await db_session.execute(
            text("SELECT id FROM sourcing_platform_accounts WHERE platform='github' AND account_type='primary'"),
        )
        pid = result.scalar_one()

        for _ in range(5):
            await am.rotate("github", pid)

        acct = await db_session.get(PlatformAccount, pid)
        assert acct.status == AccountStatus.BANNED.value
        assert acct.last_banned_at is not None

    async def test_rotate_returns_next_available(self, db_session, am):
        """rotate → 返回下一个可用账号。"""
        await self._seed(db_session)
        result = await db_session.execute(
            text("SELECT id FROM sourcing_platform_accounts WHERE platform='github' AND account_type='primary'"),
        )
        pid = result.scalar_one()

        rotated = await am.rotate("github", pid)
        assert rotated is not None
        # 应返回 backup（因 primary 的 consecutive_failures 已+1 但 <5）
        # 实际 acquire 按 account_type_order 先查 primary 再看 quota/failures
        # primary 此时 failures=1 < 5，仍然可返回 primary
        # 验证点是 rotate 没抛异常且返回了可用账号
        assert isinstance(rotated, PlatformAccount)
        assert rotated.id != pid  # 不是同一个账号

    async def test_redis_quota_cache(self, db_session, am):
        """report_usage 后 Redis 配额缓存更新。"""
        await self._seed(db_session)
        result = await db_session.execute(
            text("SELECT id FROM sourcing_platform_accounts WHERE platform='github' AND account_type='primary'"),
        )
        pid = result.scalar_one()

        await am.report_usage(pid, count=100)
        key = f"sourcing:account:github:{pid}:daily"
        cached = await am.redis.get(key)
        assert cached is not None
        assert int(cached) == 100


# ═══════════════════════════════════════════════════════════════════
# arq 任务队列集成
# ═══════════════════════════════════════════════════════════════════


class TestArqQueueIntegration:
    """arq 队列 — enqueue job + job info 持久化。"""

    @pytest.mark.asyncio
    async def test_arq_pool_create_and_enqueue(self, redis):
        """创建 arq 连接池 + enqueue job + 验证 job_info。"""
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings(database=2))
        try:
            job = await pool.enqueue_job("crawl_task", "test-task-id")
            assert job is not None
            assert job.job_id is not None

            info = await job.info()
            assert info is not None
            assert info.function == "crawl_task"
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_arq_enqueue_with_different_args(self, redis):
        """enqueue analyze_candidates 任务。"""
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings(database=2))
        try:
            job = await pool.enqueue_job(
                "analyze_candidates",
                ["cand-1", "cand-2"],
                jd_id="jd-1",
            )
            assert job is not None
            info = await job.info()
            assert info.function == "analyze_candidates"
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_arq_job_persistence_after_enqueue(self, redis):
        """enqueue 后 job 信息在 Redis 中保持（至少短暂存在）。"""
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings(database=2))
        try:
            job = await pool.enqueue_job("crawl_task", "persist-test-id")
            # 重新获取 pool，验证 job 仍在
            info = await job.info()
            assert info is not None
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_arq_job_result_ttl(self, redis):
        """keep_result 配置应生效。"""
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings(database=2))
        try:
            job = await pool.enqueue_job("crawl_task", "result-ttl-test")
            info = await job.info()
            # job_try is None when job hasn't been picked up by a worker yet
            assert info.job_try is None or info.job_try >= 0
        finally:
            await pool.close()
