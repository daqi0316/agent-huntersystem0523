"""P5-4: 个保法 PIPL service + endpoint tests (mock 模式)。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.privacy import router
    _app.include_router(router, prefix="/api/v1/privacy")
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def override_db(app, mock_db):
    from app.core.database import get_db
    from app.core.org_context import OrgContext, org_scoped_db

    async def _mock_get_db():
        yield mock_db

    async def _mock_org_scoped_db():
        org_ctx = OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr")
        yield org_ctx, mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[org_scoped_db] = _mock_org_scoped_db
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(org_scoped_db, None)


class TestPrivacyConstants:
    def test_grace_period_30_days(self):
        from app.models.privacy import GRACE_PERIOD_DAYS
        assert GRACE_PERIOD_DAYS == 30

    def test_export_retention_7_days(self):
        from app.models.privacy import EXPORT_RETENTION_DAYS
        assert EXPORT_RETENTION_DAYS == 7

    def test_user_tables_count(self):
        from app.services.privacy import USER_TABLES
        assert len(USER_TABLES) >= 15


class TestAuditLogEnum:
    def test_data_export_request_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.DATA_EXPORT_REQUEST.value == "data_export_request"

    def test_data_delete_request_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.DATA_DELETE_REQUEST.value == "data_delete_request"

    def test_data_delete_confirm_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.DATA_DELETE_CONFIRM.value == "data_delete_confirm"

    def test_data_delete_cancel_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.DATA_DELETE_CANCEL.value == "data_delete_cancel"

    def test_data_delete_hard_enum(self):
        from app.models.audit_log import AuditLogAction
        assert AuditLogAction.DATA_DELETE_HARD.value == "data_delete_hard"


class TestExportRequestService:
    @pytest.mark.asyncio
    async def test_request_export_creates_pending(self):
        from app.services.privacy import request_export
        from app.models.privacy import DataExportRequest, DataExportStatus

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=result_mock)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        req = await request_export(db, user_id="u1", org_id="o1")
        assert db.add.called
        assert db.commit.called
        assert req.status == DataExportStatus.PENDING

    @pytest.mark.asyncio
    async def test_duplicate_active_export_rejected(self):
        from app.services.privacy import request_export, PrivacyError
        from app.models.privacy import DataExportRequest, DataExportStatus

        existing = MagicMock()
        existing.status = DataExportStatus.PENDING

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=existing)
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(PrivacyError, match="已有未完成"):
            await request_export(db, user_id="u1", org_id="o1")


class TestDeleteRequestService:
    @pytest.mark.asyncio
    async def test_request_delete_creates_pending(self):
        from app.services.privacy import request_delete
        from app.models.privacy import DataDeleteStatus

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=result_mock)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        req = await request_delete(db, user_id="u1", org_id="o1")
        assert req.status == DataDeleteStatus.PENDING
        assert db.add.called

    @pytest.mark.asyncio
    async def test_confirm_delete_sets_grace_period(self):
        from app.services.privacy import confirm_delete
        from app.models.privacy import DataDeleteRequest, DataDeleteStatus, GRACE_PERIOD_DAYS
        from app.models.user import User

        req = MagicMock()
        req.id = "dr-1"
        req.user_id = "u1"
        req.status = DataDeleteStatus.PENDING

        user = MagicMock()
        user.is_active = True

        db = AsyncMock()
        async def fake_execute(stmt):
            r = MagicMock()
            if "data_delete" in str(stmt).lower():
                r.scalar_one_or_none = MagicMock(return_value=req)
            else:
                r.scalar_one_or_none = MagicMock(return_value=user)
            return r
        db.execute = fake_execute
        db.commit = AsyncMock()

        result = await confirm_delete(db, "dr-1", "u1")
        assert user.is_active is False
        assert result.status == DataDeleteStatus.GRACE_PERIOD
        assert result.scheduled_hard_delete_at is not None
        delta = (result.scheduled_hard_delete_at - result.confirmed_at).days
        assert delta >= GRACE_PERIOD_DAYS - 1

    @pytest.mark.asyncio
    async def test_cancel_delete_restores_active(self):
        from app.services.privacy import cancel_delete
        from app.models.privacy import DataDeleteRequest, DataDeleteStatus
        from app.models.user import User

        req = MagicMock()
        req.user_id = "u1"
        req.status = DataDeleteStatus.GRACE_PERIOD

        user = MagicMock()
        user.is_active = False

        db = AsyncMock()
        async def fake_execute(stmt):
            r = MagicMock()
            if "data_delete" in str(stmt).lower():
                r.scalar_one_or_none = MagicMock(return_value=req)
            else:
                r.scalar_one_or_none = MagicMock(return_value=user)
            return r
        db.execute = fake_execute
        db.commit = AsyncMock()

        result = await cancel_delete(db, "dr-1", "u1")
        assert user.is_active is True
        assert result.status == DataDeleteStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_after_hard_delete_rejected(self):
        from app.services.privacy import cancel_delete, PrivacyError
        from app.models.privacy import DataDeleteRequest, DataDeleteStatus

        req = MagicMock()
        req.user_id = "u1"
        req.status = DataDeleteStatus.HARD_DELETED

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=req)
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(PrivacyError, match="cannot cancel"):
            await cancel_delete(db, "dr-1", "u1")

    @pytest.mark.asyncio
    async def test_hard_delete_anonymizes_user(self):
        from app.services.privacy import execute_hard_delete
        from app.models.privacy import DataDeleteRequest, DataDeleteStatus

        req = MagicMock()
        req.id = "dr-1"
        req.user_id = "u1"
        req.org_id = "o1"
        req.status = DataDeleteStatus.GRACE_PERIOD
        req.scheduled_hard_delete_at = datetime.now(timezone.utc) - timedelta(days=1)
        req.placeholder_uuid = None
        req.meta = {}

        user = MagicMock()
        user.id = "u1"
        user.email = "test@x.com"
        user.name = "Test"
        user.hashed_password = "real"
        user.wechat_unionid = "u123"
        user.wechat_openid = "o123"
        user.is_active = False

        db = AsyncMock()
        async def fake_execute(stmt):
            sql = str(stmt).lower()
            r = MagicMock()
            if "data_delete" in sql:
                r.scalar_one_or_none = MagicMock(return_value=req)
            else:
                r.scalar_one_or_none = MagicMock(return_value=user)
            return r
        db.execute = fake_execute
        db.commit = AsyncMock()

        result = await execute_hard_delete(db, "dr-1")
        assert "@deleted.local" in user.email
        assert user.name == "已注销用户"
        assert user.wechat_unionid is None
        assert result.status == DataDeleteStatus.HARD_DELETED
        assert result.placeholder_uuid is not None
        assert result.placeholder_uuid.startswith("deleted_user_")


class TestPrivacyAPI:
    def test_list_exports(self, client, override_db, mock_db):
        from app.models.privacy import DataExportRequest, DataExportStatus

        req = MagicMock()
        req.id = "er-1"
        req.status = DataExportStatus.COMPLETED
        req.requested_at = datetime.now(timezone.utc)
        req.completed_at = datetime.now(timezone.utc)
        req.file_size_bytes = 1024
        req.row_counts = {"user": 1, "memberships": 2}
        req.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        req.error_message = None

        rows_mock = MagicMock()
        rows_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[req])))
        db_execute = AsyncMock(return_value=rows_mock)
        mock_db.execute = db_execute

        resp = client.get("/api/v1/privacy/export")
        assert resp.status_code == 200
        assert "data" in resp.json()
