"""Router API tests: intent classification."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_classify_screening_intent(client):
    """Screening-related keywords classify as screening."""
    resp = await client.post("/api/v1/router/classify", json={
        "text": "筛选简历",
        "use_llm": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "screening"
    assert data["method"] == "rule"
    assert data["confidence"] > 0


@pytest.mark.asyncio
async def test_classify_interview_intent(client):
    """Interview-related keywords classify as interview."""
    resp = await client.post("/api/v1/router/classify", json={
        "text": "安排面试",
        "use_llm": False,
    })
    data = resp.json()
    assert data["intent"] == "interview"


@pytest.mark.asyncio
async def test_classify_fallback_to_chat(client):
    """Unknown input falls back to chat intent."""
    resp = await client.post("/api/v1/router/classify", json={
        "text": "今天天气怎么样",
        "use_llm": False,
    })
    data = resp.json()
    assert data["intent"] == "chat"


@pytest.mark.asyncio
async def test_classify_llm_enhancement(client):
    """When LLM is available, it overrides rule classification."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "jd_generation"

    with patch("app.api.router_route.get_llm_client", return_value=mock_llm):
        resp = await client.post("/api/v1/router/classify", json={
            "text": "帮我写一份职位描述",
            "use_llm": True,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "jd_generation"
    assert data["method"] == "llm"
    assert data["confidence"] > 0.9


@pytest.mark.asyncio
async def test_classify_llm_invalid_intent_falls_back_to_rule(client):
    """LLM returns non-matching intent → falls back to rule classification."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "nonexistent_intent_xyz"

    with patch("app.api.router_route.get_llm_client", return_value=mock_llm):
        resp = await client.post("/api/v1/router/classify", json={
            "text": "帮我筛选简历",
            "use_llm": True,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "screening"
    assert data["method"] == "rule"


@pytest.mark.asyncio
async def test_classify_llm_exception_falls_back_to_rule(client):
    """LLM raises exception → falls back to rule classification."""
    mock_llm = AsyncMock()
    mock_llm.chat.side_effect = Exception("LLM unavailable")

    with patch("app.api.router_route.get_llm_client", return_value=mock_llm):
        resp = await client.post("/api/v1/router/classify", json={
            "text": "安排面试",
            "use_llm": True,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "interview"
    assert data["method"] == "rule"
