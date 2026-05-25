"""MCP Tools API tests: email and calendar simulation endpoints."""

import pytest

TOOLS_BASE = "/api/v1/tools"


@pytest.mark.asyncio
async def test_send_email_success(client):
    """发送有效邮件应返回成功。"""
    resp = await client.post(f"{TOOLS_BASE}/email/send", json={
        "to": "alice@example.com",
        "subject": "面试邀请",
        "body": "您好，恭喜进入下一轮面试...",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "sent"
    assert "alice@example.com" in data["detail"]
    assert data["message_id"].startswith("msg_")


@pytest.mark.asyncio
async def test_send_email_invalid_email(client):
    """无效邮件格式应被拒绝。"""
    resp = await client.post(f"{TOOLS_BASE}/email/send", json={
        "to": "not-an-email",
        "subject": "Test",
        "body": "Test body",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_send_email_empty_subject(client):
    """空主题应被拒绝。"""
    resp = await client.post(f"{TOOLS_BASE}/email/send", json={
        "to": "bob@example.com",
        "subject": "",
        "body": "Test body",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_send_email_with_cc_bcc(client):
    """抄送和密送应正常工作。"""
    resp = await client.post(f"{TOOLS_BASE}/email/send", json={
        "to": "primary@example.com",
        "subject": "Team Meeting",
        "body": "Reminder: team meeting at 2pm.",
        "cc": ["cc@example.com"],
        "bcc": ["bcc@example.com"],
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_query_calendar_empty(client):
    """无日期范围应返回空日历。"""
    resp = await client.get(f"{TOOLS_BASE}/calendar/query")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total"] == 0
    assert data["events"] == []


@pytest.mark.asyncio
async def test_query_calendar_with_dates(client):
    """有日期范围应返回模拟事件。"""
    resp = await client.get(f"{TOOLS_BASE}/calendar/query?date_from=2025-06-01&date_to=2025-06-30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total"] > 0
    for ev in data["events"]:
        assert "面试" in ev["title"]
        assert ev["location"] == "视频面试"


@pytest.mark.asyncio
async def test_book_calendar_success(client):
    """有效预约应成功。"""
    resp = await client.post(f"{TOOLS_BASE}/calendar/book", json={
        "title": "技术面试 - 张三",
        "start_time": "2025-06-15T10:00:00",
        "end_time": "2025-06-15T11:00:00",
        "attendee_email": "zhang@example.com",
        "location": "腾讯会议",
        "description": "第二轮技术面",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "scheduled"
    assert data["event_id"].startswith("evt_")
    assert "技术面试 - 张三" in data["detail"]
    assert "zhang@example.com" in data["detail"]


@pytest.mark.asyncio
async def test_book_calendar_missing_fields(client):
    """缺少必填字段应返回 422。"""
    resp = await client.post(f"{TOOLS_BASE}/calendar/book", json={
        "title": "面试",
        # missing start_time, end_time, attendee_email
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_book_calendar_invalid_email(client):
    """无效参与者邮箱应被拒绝。"""
    resp = await client.post(f"{TOOLS_BASE}/calendar/book", json={
        "title": "面试",
        "start_time": "2025-06-15T10:00:00",
        "end_time": "2025-06-15T11:00:00",
        "attendee_email": "not-an-email",
    })
    assert resp.status_code == 422
