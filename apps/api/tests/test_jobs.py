"""Job CRUD API tests."""

import uuid

import pytest


def _unique_email():
    return f"job-{uuid.uuid4().hex[:8]}@test.com"


async def _register(client, email):
    resp = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Pass123!", "name": "Test Admin", "role": "admin",
    })
    assert resp.status_code == 201
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_list_jobs_shows_items(client):
    email = _unique_email()
    token = await _register(client, email)
    resp = await client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "total" in resp.json()
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_create_job(client):
    email = _unique_email()
    token = await _register(client, email)
    resp = await client.post("/api/v1/jobs", json={
        "title": "高级后端工程师",
        "department": "技术部",
        "description": "负责后端系统设计与开发",
        "requirements": "5年以上Python经验",
        "location": "北京",
        "salary_range": "30k-50k",
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    assert resp.json()["data"]["title"] == "高级后端工程师"


@pytest.mark.asyncio
async def test_get_job(client):
    email = _unique_email()
    token = await _register(client, email)
    create = await client.post("/api/v1/jobs", json={
        "title": "前端工程师", "department": "技术部", "description": "前端开发",
        "requirements": "3年React", "status": "draft",
    }, headers={"Authorization": f"Bearer {token}"})
    jid = create.json()["data"]["id"]

    resp = await client.get(f"/api/v1/jobs/{jid}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "前端工程师"


@pytest.mark.asyncio
async def test_get_job_not_found(client):
    email = _unique_email()
    token = await _register(client, email)
    resp = await client.get("/api/v1/jobs/nonexistent", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_job(client):
    email = _unique_email()
    token = await _register(client, email)
    create = await client.post("/api/v1/jobs", json={
        "title": "测试职位", "department": "测试部", "description": "测试", "status": "draft",
    }, headers={"Authorization": f"Bearer {token}"})
    jid = create.json()["data"]["id"]

    resp = await client.put(f"/api/v1/jobs/{jid}", json={
        "title": "测试职位 Updated", "salary_range": "40k-60k",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "测试职位 Updated"


@pytest.mark.asyncio
async def test_delete_job(client):
    email = _unique_email()
    token = await _register(client, email)
    create = await client.post("/api/v1/jobs", json={
        "title": "待删除", "department": "测试部", "description": "删除测试", "status": "closed",
    }, headers={"Authorization": f"Bearer {token}"})
    jid = create.json()["data"]["id"]

    del_resp = await client.delete(f"/api/v1/jobs/{jid}", headers={"Authorization": f"Bearer {token}"})
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    get_resp = await client.get(f"/api/v1/jobs/{jid}", headers={"Authorization": f"Bearer {token}"})
    assert get_resp.status_code == 404
