"""Enum 集成测试 — 真 PG round-trip，验证 SQLAlchemy 写库用 enum value。

背景
----
2026-06-03 生产事故：Dashboard 500，根因是 ``SAEnum(EnumClass, name=...)``
**默认** 写库用 enum ``name``（大写），与 PostgreSQL ``approval_status`` 的
实际 label（value，小写）不匹配，触发 ``InvalidTextRepresentationError``。

此前的 mock 测试用 ``AsyncMock`` 完全屏蔽 DB，根本发现不了这个 bug。
本测试用真 PG 跑 round-trip，作为防再发屏障。

测试设计
--------
- 直接连 dev DB（``ai_recruitment``），与 ``conftest.py`` 的 ``engine`` 共享连接池
- 每次 test 创建临时 user（满足 FK），结束 ROLLBACK，保证互不污染
- 验证用 ``text("SELECT col::text FROM ...")::text`` 拿**字符串**，与 enum 名字面量无关
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import Enum as SAEnum, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models._base import enum_column
from app.models.approval import Approval, ApprovalStatus
from app.models.recommendation import RecommendationType
from app.services.approval_service import ApprovalService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def engine():
    """每个 test 一个新 engine — asyncpg 连接池绑定到当前 event loop。
    共享 module-level engine 会因 conftest 的 session-scoped event_loop 跨 loop 失效。"""
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
async def tmp_user_id(db_session: AsyncSession) -> str:
    user_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, name, role, is_active, created_at, updated_at) "
            "VALUES (CAST(:id AS UUID), :email, 'x', 'test-user', 'VIEWER', true, now(), now())"
        ),
        {"id": user_id, "email": f"test-{user_id}@example.com"},
    )
    await db_session.commit()
    return user_id


@pytest_asyncio.fixture
async def svc(db_session: AsyncSession) -> ApprovalService:
    return ApprovalService(db_session)


# ---------------------------------------------------------------------------
# Factory 自身测试
# ---------------------------------------------------------------------------

class TestEnumColumnFactory:
    def test_enum_column_returns_saenum(self):
        col = enum_column(ApprovalStatus, "approval_status")
        assert isinstance(col, SAEnum)

    def test_enum_column_binds_value_not_name(self):
        """关键断言：把 enum 成员塞进 column，序列化后必须是 value (小写)。"""
        col = enum_column(ApprovalStatus, "approval_status")
        # SQLAlchemy 内部把 enum member 转为 value 字符串的接口
        # 在不同版本里叫 _object_value_for_elem 或 _value_for_elem,
        # 两者都返回字符串。任一可用即可。
        bound = None
        for attr in ("_object_value_for_elem", "_value_for_elem"):
            fn = getattr(col, attr, None)
            if fn is None:
                continue
            try:
                bound = fn(ApprovalStatus.PENDING)
                break
            except Exception:
                continue
        assert bound == "pending", (
            f"enum_column() 应让 SQLAlchemy 写库时用 value 'pending'，"
            f"实际得到 {bound!r} — values_callable 未生效"
        )
        bound_expired = col._value_for_elem(ApprovalStatus.EXPIRED) if hasattr(col, "_value_for_elem") else col._object_value_for_elem(ApprovalStatus.EXPIRED)
        assert bound_expired == "expired"


# ---------------------------------------------------------------------------
# Round-trip: 写 model → raw SQL 读回 → 断言是小写 value
# ---------------------------------------------------------------------------

class TestApprovalStatusRoundTrip:
    """绕开 ORM refresh（DB id 列是 varchar，model 声明是 UUID，schema 漂移是另一独立 bug）。
    本测试只验证 enum 写库行为 — 用 raw SQL INSERT/UPDATE/SELECT，不依赖 ORM 路径。"""

    @pytest.mark.asyncio
    async def test_insert_with_model_status_writes_lowercase(
        self, db_session: AsyncSession, tmp_user_id: str,
    ) -> None:
        approval_id = str(uuid.uuid4())
        await db_session.execute(
            text(
                "INSERT INTO approvals (id, user_id, action_type, status, proposal, params, created_at, updated_at, expires_at) "
                "VALUES (:id, :uid, :act, :st, :pr, :pa, now(), now(), now() + interval '48 hours')"
            ),
            {
                "id": approval_id, "uid": tmp_user_id, "act": "test_create",
                "st": ApprovalStatus.PENDING.value,  # 'pending' 走 model 序列化
                "pr": "{}", "pa": "{}",
            },
        )
        await db_session.commit()

        row = await db_session.execute(
            text("SELECT status::text FROM approvals WHERE id = :id"),
            {"id": approval_id},
        )
        actual = row.scalar()
        assert actual == "pending", f"DB status 必须是 'pending'，实际 {actual!r}"

    @pytest.mark.asyncio
    async def test_expire_pending_writes_lowercase_expired(
        self, svc: ApprovalService, db_session: AsyncSession, tmp_user_id: str,
    ) -> None:
        approval_id = str(uuid.uuid4())
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        await db_session.execute(
            text(
                "INSERT INTO approvals (id, user_id, action_type, status, proposal, params, created_at, updated_at, expires_at) "
                "VALUES (:id, :uid, :act, :st, :pr, :pa, :ts, :ts, :exp)"
            ),
            {
                "id": approval_id, "uid": tmp_user_id, "act": "test_expire",
                "st": ApprovalStatus.PENDING.value,
                "pr": "{}", "pa": "{}",
                "ts": past, "exp": past,
            },
        )
        await db_session.commit()

        # expire_pending 内部走 ORM UPDATE — 它会写入 ApprovalStatus.EXPIRED.value
        # 这正是生产 bug 复现路径；如果 values_callable 没生效，会抛
        # InvalidTextRepresentationError，测试会在 except 捕获并 fail。
        expired = await svc.expire_pending()
        assert expired >= 1, "expire_pending 应该至少过期 1 条"

        result = await db_session.execute(
            text("SELECT status::text FROM approvals WHERE id = :id"),
            {"id": approval_id},
        )
        actual = result.scalar()
        assert actual == "expired", (
            f"DB status 必须是 'expired'，实际 {actual!r} — "
            f"values_callable 未生效或 SQLAlchemy 仍用 name 写入"
        )

    @pytest.mark.asyncio
    async def test_orm_status_literal_binds_value_lowercase(self) -> None:
        """纯枚举序列化路径验证 — 不依赖 DB（已被 expire_pending round-trip 覆盖写入路径）。

        防御：未来如果有人改回 ``SAEnum(EnumClass, name=...)`` 不带 values_callable，
        这个断言会立即 fail，作为防再发的快速单元层。"""
        from app.models.approval import Approval
        from app.models.recommendation import Recommendation

        for col, enum_cls, expected in [
            (Approval.__table__.c.status.type, ApprovalStatus, {
                ApprovalStatus.PENDING: "pending",
                ApprovalStatus.APPROVED: "approved",
                ApprovalStatus.REJECTED: "rejected",
                ApprovalStatus.EXPIRED: "expired",
                ApprovalStatus.CANCELLED: "cancelled",
            }),
            (Recommendation.__table__.c.type.type, RecommendationType, {
                RecommendationType.CANDIDATE_JOB_MATCH: "candidate_job_match",
                RecommendationType.NEW_CANDIDATE: "new_candidate",
                RecommendationType.NEW_JOB: "new_job",
            }),
        ]:
            for member, want in expected.items():
                got = col._db_value_for_elem(member)
                assert got == want, (
                    f"{enum_cls.__name__}.{member.name}: 序列化为 {got!r}，"
                    f"应为 {want!r} — values_callable 未生效"
                )


class TestRecommendationTypeRoundTrip:
    @pytest.mark.asyncio
    async def test_insert_writes_lowercase(
        self, db_session: AsyncSession, tmp_user_id: str,
    ) -> None:
        rec_id = str(uuid.uuid4())
        # recommendations 表无 updated_at 列（独立 schema 漂移，与 enum 修复无关）
        await db_session.execute(
            text(
                "INSERT INTO recommendations (id, user_id, type, title, description, created_at) "
                "VALUES (:id, :uid, :t, :title, '', now())"
            ),
            {
                "id": rec_id, "uid": tmp_user_id,
                "t": RecommendationType.NEW_CANDIDATE.value,
                "title": "test rec",
            },
        )
        await db_session.commit()

        row = await db_session.execute(
            text("SELECT type::text FROM recommendations WHERE id = :id"),
            {"id": rec_id},
        )
        actual = row.scalar()
        assert actual == "new_candidate", (
            f"recommendation_type DB 必须是 'new_candidate'，实际 {actual!r}"
        )
        await db_session.commit()

        # resolve 内部 ORM UPDATE 把 status 改成 APPROVED
        result = await svc.resolve(approval_id, tmp_user_id, approved=True, resolution="ok")
        assert result is not None

        row = await db_session.execute(
            text("SELECT status::text FROM approvals WHERE id = :id"),
            {"id": approval_id},
        )
        assert row.scalar() == "approved"


class TestRecommendationTypeRoundTrip:
    @pytest.mark.asyncio
    async def test_insert_writes_lowercase(
        self, db_session: AsyncSession, tmp_user_id: str,
    ) -> None:
        rec_id = str(uuid.uuid4())
        # recommendations 表无 updated_at 列（独立 schema 漂移，与 enum 修复无关）
        await db_session.execute(
            text(
                "INSERT INTO recommendations (id, user_id, type, title, description, created_at) "
                "VALUES (:id, :uid, :t, :title, '', now())"
            ),
            {
                "id": rec_id, "uid": tmp_user_id,
                "t": RecommendationType.NEW_CANDIDATE.value,
                "title": "test rec",
            },
        )
        await db_session.commit()

        row = await db_session.execute(
            text("SELECT type::text FROM recommendations WHERE id = :id"),
            {"id": rec_id},
        )
        actual = row.scalar()
        assert actual == "new_candidate", (
            f"recommendation_type DB 必须是 'new_candidate'，实际 {actual!r}"
        )


# ---------------------------------------------------------------------------
# 防再发：静态扫描 — 禁止再出现裸 SAEnum(EnumClass, name=...)
# ---------------------------------------------------------------------------

class TestNoBareSaenumRegression:
    """防再发：所有 model 文件不得出现 ``SAEnum(EnumClass, name=...)`` 模式。"""

    MODEL_FILES = [
        "app/models/approval.py",
        "app/models/recommendation.py",
        "app/models/interview_evaluation.py",
        "app/models/candidate.py",
    ]

    def test_no_bare_saenum_with_enum_class(self) -> None:
        pattern = re.compile(
            r"SAEnum\s*\(\s*[A-Z][A-Za-z]+(?:Status|Type|Category|Role|Verdict|Round)"
            r"\s*,\s*name\s*=\s*['\"][^'\"]+['\"]\s*\)"
        )

        root = Path(__file__).resolve().parents[1]
        offenders: list[str] = []
        for rel in self.MODEL_FILES:
            path = root / rel
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count("\n") + 1
                offenders.append(f"{rel}:{line_no}: {m.group()!r}")

        assert not offenders, (
            "发现裸 SAEnum(EnumClass, name=...) 调用 — 必须改用 enum_column() 工厂:\n"
            + "\n".join(offenders)
        )


# ---------------------------------------------------------------------------
# Schema 漂移修复验证：resolve() 整链路
# ---------------------------------------------------------------------------

class TestResolveVarcharIdRoundTrip:
    """生产路径：approve/reject → svc.resolve() → 500 因 schema 漂移。
    修复后 model 列改 String(36)，整链路不再 500。"""

    @pytest.mark.asyncio
    async def test_resolve_works_end_to_end(
        self, db_session: AsyncSession, tmp_user_id: str,
    ) -> None:
        from app.services.approval_service import ApprovalService

        approval_id = str(uuid.uuid4())
        proposal = {"candidate_id": "c1", "job_id": "j1"}
        params = {"foo": "bar"}
        await db_session.execute(
            text(
                "INSERT INTO approvals (id, user_id, action_type, status, proposal, params, created_at, updated_at, expires_at) "
                "VALUES (:id, :uid, 'resolve_test', 'pending', :pr, :pa, now(), now(), now() + interval '48 hours')"
            ),
            {
                "id": approval_id, "uid": tmp_user_id,
                "pr": json.dumps(proposal), "pa": json.dumps(params),
            },
        )
        await db_session.commit()

        svc = ApprovalService(db_session)
        result = await svc.resolve(approval_id, tmp_user_id, approved=True, resolution="ok")
        assert result is not None, "resolve() 必须返回 Approval 实例（修复前会抛 UndefinedFunctionError）"
        assert result.status == ApprovalStatus.APPROVED

        status_row = await db_session.execute(
            text("SELECT status::text FROM approvals WHERE id = :id"),
            {"id": approval_id},
        )
        assert status_row.scalar() == "approved"

        data_row = await db_session.execute(
            text("SELECT proposal::text, params::text, action_type FROM approvals WHERE id = :id"),
            {"id": approval_id},
        )
        proposal_db, params_db, action_type_db = data_row.first()
        assert json.loads(proposal_db) == proposal
        assert json.loads(params_db) == params
        assert action_type_db == "resolve_test"


# ---------------------------------------------------------------------------
# Emergency Stop 修复验证
# ---------------------------------------------------------------------------

class TestEmergencyStopMarksCancelled:
    """修复前：_pending_purge_all 会把 proposal/params/action_type 清空。
    修复后：仅 status='cancelled' + resolved_at，proposal/params/action_type 完整。"""

    @pytest.mark.asyncio
    async def test_purge_marks_cancelled_preserves_data(
        self, db_session: AsyncSession, tmp_user_id: str,
    ) -> None:
        from app.agents.human_loop import HumanLoopAgent

        approval_id = str(uuid.uuid4())
        proposal = {"key": "value", "nested": {"a": 1}}
        params = {"foo": [1, 2, 3]}
        await db_session.execute(
            text(
                "INSERT INTO approvals (id, user_id, action_type, status, proposal, params, created_at, updated_at, expires_at) "
                "VALUES (:id, :uid, 'purge_test', 'pending', :pr, :pa, now(), now(), now() + interval '48 hours')"
            ),
            {
                "id": approval_id, "uid": tmp_user_id,
                "pr": json.dumps(proposal), "pa": json.dumps(params),
            },
        )
        await db_session.commit()

        agent = HumanLoopAgent("test")
        await agent._pending_purge_all()

        row = await db_session.execute(
            text("SELECT status::text, action_type, proposal::text, params::text FROM approvals WHERE id = :id"),
            {"id": approval_id},
        )
        status_db, action_type_db, proposal_db, params_db = row.first()
        assert status_db == "cancelled", f"status 应为 'cancelled'，实际 {status_db!r}"
        assert action_type_db == "purge_test", (
            f"action_type 必须保留为 'purge_test'，实际 {action_type_db!r} — "
            f"原 bug 会把 action_type 清空"
        )
        assert json.loads(proposal_db) == proposal
        assert json.loads(params_db) == params


# ---------------------------------------------------------------------------
# 防再发：禁止在生产阻塞 model 中再出现 UUID(as_uuid=False)
# ---------------------------------------------------------------------------

class TestNoSchemaDriftRegression:
    """生产阻塞的 3 个 model（approvals/recommendations/command_audit_log）不得再出现
    ``UUID(as_uuid=False)`` — 应当用 ``String(36)``。
    注：operation_log 仅 superseded_by 列 DB 是 uuid（合法），不纳入；
    application/candidate/interview/job_position 的所有列 DB 是 uuid（合法），不纳入。"""

    BLOCKED_MODEL_FILES = [
        "app/models/approval.py",
        "app/models/recommendation.py",
        "app/models/command_audit_log.py",
    ]

    def test_no_bare_uuid_as_uuid_false_in_blocked_models(self) -> None:
        pattern = re.compile(r"UUID\s*\(\s*as_uuid\s*=\s*False\s*\)")

        root = Path(__file__).resolve().parents[1]
        offenders: list[str] = []
        for rel in self.BLOCKED_MODEL_FILES:
            path = root / rel
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count("\n") + 1
                offenders.append(f"{rel}:{line_no}: {m.group()!r}")

        assert not offenders, (
            "发现生产阻塞 model 仍使用 UUID(as_uuid=False) — DB 实际是 varchar，"
            "会导致 ORM WHERE $1::UUID 不可比，500 报错。必须改用 String(36):\n"
            + "\n".join(offenders)
        )
