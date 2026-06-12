"""Auth API tests with mocked dependencies — no real DB needed."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.auth import router
    _app.include_router(router, prefix="/api/v1/auth")
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

    async def _mock_db():
        yield mock_db

    async def _fake_org_scoped_db():
        yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), mock_db

    app.dependency_overrides[get_db] = _mock_db
    app.dependency_overrides[org_scoped_db] = _fake_org_scoped_db
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(org_scoped_db, None)


@pytest.fixture
def override_auth(app):
    """Override get_current_user_id to return a fixed user_id."""
    from app.core.dependencies import get_current_user_id

    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


def _mock_user(**kwargs):
    u = MagicMock()
    u.id = kwargs.get("id", "user-1")
    u.email = kwargs.get("email", "test@test.com")
    u.name = kwargs.get("name", "Test User")
    u.role = MagicMock()
    u.role.value = kwargs.get("role", "hr")
    u.is_active = kwargs.get("is_active", True)
    u.created_at = kwargs.get("created_at", "2025-01-01")
    return u


class TestRegister:
    ROUTE = "/api/v1/auth/register"

    def test_success(self, client, override_db):
        mock_user = _mock_user()
        with (
            patch("app.api.auth.UserService.register") as mock_register,
            patch("app.api.auth.get_or_create_default_org") as mock_org,
            patch("app.api.auth.create_access_token") as mock_token,
        ):
            mock_register.return_value = (mock_user, {"access_token": "jwt-token-abc"})
            mock_org.return_value = "test-org-id"
            mock_token.return_value = "jwt-token-abc"
            resp = client.post(self.ROUTE, json={
                "email": "new@test.com",
                "password": "SecurePass123!",
                "name": "New User",
                "role": "viewer",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["access_token"] == "jwt-token-abc"

    def test_duplicate_email(self, client, override_db):
        with patch("app.api.auth.UserService.register") as mock_register:
            mock_register.side_effect = HTTPException(status_code=409, detail="Email already registered")
            resp = client.post(self.ROUTE, json={
                "email": "dup@test.com",
                "password": "SecurePass123!",
                "name": "Dup User",
            })
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Email already registered"

    def test_invalid_email(self, client, override_db):
        resp = client.post(self.ROUTE, json={
            "email": "not-email",
            "password": "SecurePass123!",
            "name": "User",
        })
        assert resp.status_code == 422

    def test_missing_password(self, client, override_db):
        resp = client.post(self.ROUTE, json={
            "email": "test@test.com",
            "name": "No Pass",
        })
        assert resp.status_code == 422


class TestLogin:
    ROUTE = "/api/v1/auth/login"

    def test_success(self, client, override_db):
        mock_user = _mock_user()
        with (
            patch("app.api.auth.UserService.login") as mock_login,
            patch("app.api.auth.get_or_create_default_org") as mock_org,
            patch("app.api.auth.create_access_token") as mock_token,
        ):
            mock_login.return_value = (mock_user, {"access_token": "jwt-token-xyz"})
            mock_org.return_value = "test-org-id"
            mock_token.return_value = "jwt-token-xyz"
            resp = client.post(self.ROUTE, json={
                "email": "test@test.com",
                "password": "Pass123!",
            })
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "jwt-token-xyz"

    def test_wrong_password(self, client, override_db):
        with patch("app.api.auth.UserService.login") as mock_login:
            mock_login.side_effect = HTTPException(status_code=401, detail="Invalid email or password")
            resp = client.post(self.ROUTE, json={
                "email": "test@test.com",
                "password": "wrong",
            })
        assert resp.status_code == 401
        assert "Invalid email or password" in resp.json()["detail"]

    def test_nonexistent_user(self, client, override_db):
        with patch("app.api.auth.UserService.login") as mock_login:
            mock_login.side_effect = HTTPException(status_code=401, detail="Invalid email or password")
            resp = client.post(self.ROUTE, json={
                "email": "nonexistent@test.com",
                "password": "Pass123!",
            })
        assert resp.status_code == 401


class TestGetMe:
    ROUTE = "/api/v1/auth/me"

    def test_with_token(self, client, override_db, override_auth):
        """GET /me returns the current user profile."""
        mock_user = _mock_user()
        # Configure db.execute().all() for the membership query in get_me
        from app.core.database import get_db
        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db = AsyncMock()
        mock_db.execute.return_value = execute_result

        async def _mock_db():
            yield mock_db

        from app.core.org_context import OrgContext, org_scoped_db

        async def _fake_org_scoped_db():
            yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), mock_db

        client._transport.app.dependency_overrides[get_db] = _mock_db
        client._transport.app.dependency_overrides[org_scoped_db] = _fake_org_scoped_db

        with patch("app.api.auth.UserService.get_by_id") as mock_get:
            mock_get.return_value = mock_user
            resp = client.get(self.ROUTE)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test@test.com"
        assert data["id"] == "user-1"
