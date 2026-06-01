from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole
from app.services.user import UserService


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = AsyncMock(return_value=None)
    db.delete = AsyncMock(return_value=None)
    return db


class TestRegister:
    async def test_creates_user_and_returns_token(self, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr

        from app.schemas.auth import RegisterRequest

        data = RegisterRequest(
            email="new@test.com", password="secret123", name="Test User"
        )
        user, token_resp = await UserService.register(mock_db, data)
        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_db.refresh.called
        assert token_resp.access_token

    async def test_raises_on_duplicate_email(self, mock_db):
        existing = Mock(spec=User)
        mr = Mock()
        mr.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mr

        from app.schemas.auth import RegisterRequest

        data = RegisterRequest(email="dup@test.com", password="pw", name="Dup")
        with pytest.raises(HTTPException) as exc:
            await UserService.register(mock_db, data)
        assert exc.value.status_code == 409


class TestLogin:
    async def test_success(self, mock_db):
        user = Mock(spec=User)
        user.id = "user-1"
        user.email = "test@test.com"
        user.hashed_password = Mock()
        user.is_active = True
        user.role = Mock()
        user.role.value = "hr"

        mr = Mock()
        mr.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mr

        with patch("app.services.user.verify_password", return_value=True):
            from app.schemas.auth import LoginRequest
            user_resp, token_resp = await UserService.login(
                mock_db, LoginRequest(email="test@test.com", password="pw")
            )
            assert token_resp.access_token

    async def test_invalid_credentials(self, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr

        from app.schemas.auth import LoginRequest
        with pytest.raises(HTTPException) as exc:
            await UserService.login(
                mock_db, LoginRequest(email="no@test.com", password="wrong")
            )
        assert exc.value.status_code == 401

    async def test_inactive_user(self, mock_db):
        user = Mock(spec=User)
        user.id = "user-1"
        user.hashed_password = Mock()
        user.is_active = False

        mr = Mock()
        mr.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mr

        with patch("app.services.user.verify_password", return_value=True):
            from app.schemas.auth import LoginRequest
            with pytest.raises(HTTPException) as exc:
                await UserService.login(
                    mock_db, LoginRequest(email="inactive@test.com", password="pw")
                )
            assert exc.value.status_code == 403


class TestGetByEmail:
    async def test_found(self, mock_db):
        user = Mock(spec=User)
        mr = Mock()
        mr.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mr
        result = await UserService.get_by_email(mock_db, "test@test.com")
        assert result is not None

    async def test_not_found(self, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        result = await UserService.get_by_email(mock_db, "none@test.com")
        assert result is None


class TestGetById:
    async def test_found(self, mock_db):
        user = Mock(spec=User)
        mr = Mock()
        mr.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mr
        result = await UserService.get_by_id(mock_db, "user-1")
        assert result is not None

    async def test_not_found(self, mock_db):
        mr = Mock()
        mr.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mr
        with pytest.raises(HTTPException) as exc:
            await UserService.get_by_id(mock_db, "no-user")
        assert exc.value.status_code == 404


class TestToResponse:
    def test_converts_user(self):
        user = Mock(spec=User)
        user.id = "u-1"
        user.email = "a@b.com"
        user.name = "A"
        user.role = Mock()
        user.role.value = "admin"
        user.is_active = True
        from datetime import datetime, timezone
        user.created_at = datetime.now(timezone.utc)
        resp = UserService.to_response(user)
        assert resp.email == "a@b.com"
        assert resp.role == "admin"
