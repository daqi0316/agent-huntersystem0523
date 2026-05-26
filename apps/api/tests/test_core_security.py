from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.dependencies import get_current_user_id, get_optional_user_id
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

MOCK_SECRET = "test-secret-key-for-testing"
MOCK_ALGO = "HS256"
MOCK_EXP_HOURS = 24


@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.core.security.settings") as mock_s:
        mock_s.jwt_secret = MOCK_SECRET
        mock_s.jwt_algorithm = MOCK_ALGO
        mock_s.jwt_expiration_hours = MOCK_EXP_HOURS
        yield mock_s


class TestHashPassword:
    def test_hash_differs_from_input(self):
        hashed = hash_password("hello")
        assert hashed != "hello"
        assert isinstance(hashed, str)

    def test_hash_is_deterministic(self):
        h1 = hash_password("hello")
        h2 = hash_password("hello")
        assert h1 != h2


class TestVerifyPassword:
    def test_correct_password(self):
        hashed = hash_password("correctpw")
        assert verify_password("correctpw", hashed) is True

    def test_incorrect_password(self):
        hashed = hash_password("correctpw")
        assert verify_password("wrongpw", hashed) is False


class TestCreateAccessToken:
    def test_contains_sub(self):
        token = create_access_token("user-123")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-123"

    def test_contains_role_default(self):
        token = create_access_token("user-123")
        payload = decode_access_token(token)
        assert payload["role"] == "user"

    def test_contains_custom_role(self):
        token = create_access_token("user-123", role="admin")
        payload = decode_access_token(token)
        assert payload["role"] == "admin"

    def test_expiry_in_future(self):
        before = datetime.now(timezone.utc)
        token = create_access_token("user-123")
        payload = decode_access_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > before
        assert exp < before + timedelta(hours=MOCK_EXP_HOURS + 1)


class TestDecodeAccessToken:
    def test_decode_valid_token(self):
        token = create_access_token("u1")
        payload = decode_access_token(token)
        assert payload["sub"] == "u1"

    def test_decode_garbage_token(self):
        payload = decode_access_token("garbage.token.here")
        assert payload == {}

    def test_decode_empty_token(self):
        payload = decode_access_token("")
        assert payload == {}

    def test_decode_expired_token_returns_empty(self):
        with patch("app.core.security.settings") as mock_s:
            mock_s.jwt_secret = MOCK_SECRET
            mock_s.jwt_algorithm = MOCK_ALGO
            mock_s.jwt_expiration_hours = -1
            token = create_access_token("u1")
        payload = decode_access_token(token)
        assert payload == {}


class TestDependencies:
    @pytest.mark.asyncio
    async def test_get_current_user_id_valid(self):
        token = create_access_token("u-42")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        result = await get_current_user_id(creds)
        assert result == "u-42"

    @pytest.mark.asyncio
    async def test_get_current_user_id_invalid_token(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad.token")
        with pytest.raises(HTTPException) as exc:
            await get_current_user_id(creds)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_optional_user_id_valid(self):
        token = create_access_token("u-99")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        result = await get_optional_user_id(creds)
        assert result == "u-99"

    @pytest.mark.asyncio
    async def test_get_optional_user_id_none_when_no_credentials(self):
        result = await get_optional_user_id(None)
        assert result is None
