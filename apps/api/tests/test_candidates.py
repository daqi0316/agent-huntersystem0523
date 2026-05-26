"""Candidate CRUD API tests."""

import uuid

import pytest


def _unique_email(prefix="cand"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}@test.com"


async def _register(client, email):
    resp = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Test Admin", "role": "admin",
    })
    assert resp.status_code == 201
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_list_candidates_shows_items(client):
    email = _unique_email()
    token = await _register(client, email)
    resp = await client.get("/api/v1/candidates", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "total" in resp.json()
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_create_candidate(client):
    email = _unique_email()
    token = await _register(client, email)
    resp = await client.post("/api/v1/candidates", json={
        "name": "张三",
        "email": _unique_email("cand-create"),
        "phone": "13800138001",
        "source": "linkedin",
        "status": "active",
        "skills": ["Python", "FastAPI"],
        "experience_years": 5,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    assert resp.json()["data"]["name"] == "张三"


@pytest.mark.asyncio
async def test_get_candidate(client):
    email = _unique_email()
    token = await _register(client, email)
    cand_email = _unique_email("cand-get")
    create = await client.post("/api/v1/candidates", json={
        "name": "李四", "email": cand_email, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    cid = create.json()["data"]["id"]

    resp = await client.get(f"/api/v1/candidates/{cid}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "李四"


@pytest.mark.asyncio
async def test_get_candidate_not_found(client):
    email = _unique_email()
    token = await _register(client, email)
    resp = await client.get("/api/v1/candidates/nonexistent", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_candidate(client):
    email = _unique_email()
    token = await _register(client, email)
    cand_email = _unique_email("cand-upd")
    create = await client.post("/api/v1/candidates", json={
        "name": "王五", "email": cand_email, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    cid = create.json()["data"]["id"]

    resp = await client.put(f"/api/v1/candidates/{cid}", json={
        "name": "王五 Updated", "status": "archived",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "王五 Updated"
    assert resp.json()["data"]["status"] == "archived"


@pytest.mark.asyncio
async def test_delete_candidate(client):
    email = _unique_email()
    token = await _register(client, email)
    cand_email = _unique_email("cand-del")
    create = await client.post("/api/v1/candidates", json={
        "name": "赵六", "email": cand_email, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    cid = create.json()["data"]["id"]

    del_resp = await client.delete(f"/api/v1/candidates/{cid}", headers={"Authorization": f"Bearer {token}"})
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    get_resp = await client.get(f"/api/v1/candidates/{cid}", headers={"Authorization": f"Bearer {token}"})
    assert get_resp.status_code == 404
