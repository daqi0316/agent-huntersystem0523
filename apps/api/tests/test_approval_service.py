"""Tests for ApprovalService — DB-persisted approval management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.approval import Approval, ApprovalStatus
from app.services.approval_service import ApprovalService, DEFAULT_EXPIRY_HOURS


def _make_approval(
    approval_id: str | None = None,
    user_id: str = "user-1",
    action_type: str = "screening_approve",
    status: ApprovalStatus = ApprovalStatus.PENDING,
    expires_at: datetime | None = None,
    resolved_at: datetime | None = None,
) -> MagicMock:
    """Factory for a mock Approval row."""
    now = datetime.now(timezone.utc)
    a = MagicMock(spec=Approval)
    a.id = approval_id or str(uuid4())
    a.user_id = user_id
    a.action_type = action_type
    a.status = status
    a.proposal = {"candidate_id": "c1", "job_id": "j1"}
    a.params = {}
    a.candidate_email = "test@example.com"
    a.created_at = now
    a.expires_at = expires_at or (now + timedelta(hours=DEFAULT_EXPIRY_HOURS))
    a.resolved_at = resolved_at
    a.resolver_id = None
    a.resolution = None
    return a


class TestApprovalServiceCreate:
    @pytest.mark.asyncio
    async def test_create_approval(self) -> None:
        db = AsyncMock()
        svc = ApprovalService(db)
        with patch("app.services.approval_service.event_bus") as mock_bus:
            result = await svc.create(
                user_id="u1",
                action_type="screening_approve",
                proposal={"candidate_id": "c1"},
            )
        assert result.user_id == "u1"
        assert result.action_type == "screening_approve"
        assert result.status == ApprovalStatus.PENDING
        assert result.proposal == {"candidate_id": "c1"}
        db.add.assert_called_once()
        db.commit.assert_called()
        db.refresh.assert_called()
        mock_bus.publish.assert_called_once_with("approval.created", {
            "approval_id": result.id,
            "action_type": "screening_approve",
            "status": "pending",
            "expires_at": result.expires_at.isoformat(),
        })

    @pytest.mark.asyncio
    async def test_create_with_custom_expiry(self) -> None:
        db = AsyncMock()
        svc = ApprovalService(db)
        await svc.create(user_id="u1", action_type="x", proposal={}, expiry_hours=24)
        added = db.add.call_args[0][0]
        assert (added.expires_at - added.created_at) == timedelta(hours=24)

    @pytest.mark.asyncio
    async def test_create_empty_target_is_none(self) -> None:
        db = AsyncMock()
        svc = ApprovalService(db)
        result = await svc.create(
            user_id="u1", action_type="x", proposal={}, target_type="", target_id=""
        )
        assert result.target_type is None
        assert result.target_id is None


class TestApprovalServiceResolve:
    @pytest.mark.asyncio
    async def test_resolve_approved(self) -> None:
        db = AsyncMock()
        approval = _make_approval()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=approval)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        with patch("app.services.approval_service.event_bus") as mock_bus:
            result = await svc.resolve(approval.id, "resolver-1", approved=True, resolution="ok")
        assert result is not None
        assert result.status == ApprovalStatus.APPROVED
        assert result.resolver_id == "resolver-1"
        assert result.resolution == "ok"
        assert result.resolved_at is not None
        db.commit.assert_called()
        mock_bus.publish.assert_called_once_with("approval.resolved", {
            "approval_id": approval.id,
            "action_type": approval.action_type,
            "status": "approved",
            "resolver_id": "resolver-1",
        })

    @pytest.mark.asyncio
    async def test_resolve_rejected(self) -> None:
        db = AsyncMock()
        approval = _make_approval()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=approval)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        result = await svc.resolve(approval.id, "resolver-1", approved=False)
        assert result is not None
        assert result.status == ApprovalStatus.REJECTED

    @pytest.mark.asyncio
    async def test_resolve_not_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        result = await svc.resolve("nonexistent-id", "r1", approved=True)
        assert result is None
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_empty_resolution_is_none(self) -> None:
        db = AsyncMock()
        approval = _make_approval()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=approval)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        result = await svc.resolve(approval.id, "r1", approved=True, resolution="")
        assert result is not None
        assert result.resolution is None


class TestApprovalServiceExpirePending:
    @pytest.mark.asyncio
    async def test_expire_pending_updates_rows(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        with patch("app.services.approval_service.event_bus") as mock_bus:
            count = await svc.expire_pending()
        assert count == 3
        db.commit.assert_called()
        mock_bus.publish.assert_called_once_with("approval.expired", {"count": 3})

    @pytest.mark.asyncio
    async def test_expire_pending_none_expired(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        count = await svc.expire_pending()
        assert count == 0


class TestApprovalServiceListPending:
    @pytest.mark.asyncio
    async def test_list_pending_returns_formatted(self) -> None:
        db = AsyncMock()
        a1 = _make_approval(approval_id="a1")
        a2 = _make_approval(approval_id="a2")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[a1, a2])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        result = await svc.list_pending()
        assert len(result) == 2
        assert result[0]["approval_id"] == "a1"
        assert result[0]["status"] == "pending"
        assert "proposal" in result[0]

    @pytest.mark.asyncio
    async def test_list_pending_empty(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        result = await svc.list_pending()
        assert result == []


class TestApprovalServiceListHistory:
    @pytest.mark.asyncio
    async def test_list_history_returns_resolved(self) -> None:
        db = AsyncMock()
        a1 = _make_approval(status=ApprovalStatus.APPROVED, resolved_at=datetime.now(timezone.utc))
        a2 = _make_approval(status=ApprovalStatus.REJECTED, resolved_at=datetime.now(timezone.utc))
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[a1, a2])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        result = await svc.list_history()
        assert len(result) == 2
        assert result[0]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_list_history_empty(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        result = await svc.list_history()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_history_respects_limit(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        await svc.list_history(limit=10)
        call_stmt = db.execute.call_args[0][0]
        compiled = str(call_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT" in compiled.upper()


class TestApprovalServiceGet:
    @pytest.mark.asyncio
    async def test_get_found(self) -> None:
        db = AsyncMock()
        approval = _make_approval(approval_id="find-me")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=approval)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        result = await svc.get("find-me")
        assert result is not None
        assert result.id == "find-me"

    @pytest.mark.asyncio
    async def test_get_not_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ApprovalService(db)
        result = await svc.get("nonexistent")
        assert result is None
