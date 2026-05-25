"""Auth API tests: register, login, me, error cases."""

import uuid

import pytest


def _unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@test.com"


@pytest.mark.asyncio
async def test_register_success(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": _unique_email(),
        "password": "SecurePass123!",
        "name": "New User",
        "role": "viewer",
    })
    assert resp.status_code == 201
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    email = _unique_email()
    await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "User",
    })
    resp = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "User",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "not-an-email", "password": "Pass123!", "name": "User",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client):
    email = _unique_email()
    await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Login User",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "Pass123!",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    email = _unique_email()
    await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Correct1!", "name": "User",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "WrongPass1!",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "nobody@test.com", "password": "Pass123!",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_token(client):
    email = _unique_email()
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Me User",
    })
    token = reg.json()["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    assert resp.json()["email"] == email


@pytest.mark.asyncio
async def test_get_me_no_token(client):
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(client):
    resp = await client.get("/api/v1/auth/me", headers={
        "Authorization": "Bearer invalidtoken123",
    })
    assert resp.status_code == 401
