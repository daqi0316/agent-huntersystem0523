"""v1.1.1 search_candidates skills filter 真生效测试.

背景 (v1.1 ship report §7): handler 接受 skills 参数但未传给 svc.list,
E2E 发现后决定修. 修法: svc.list 加 skills 参数 + PostgreSQL array overlap
算子 `&&` (Candidate.skills && ['Python'] = 至少含 1 个 Python).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import engine
from app.core.dependencies import get_current_user_id
from app.core.org_context import OrgContext, org_scoped_db
from app.main import app
from app.schemas.resume import ExtractedCandidate
from app.tools.candidate_search import handlers as search_handlers
from app.tools.resume_parser import handlers as resume_handlers


PYTHON_TEXT = "张三 Python FastAPI 5年 13800138001"
GO_TEXT = "李四 Go Kubernetes 3年 13800138002"


def _ext(name: str, uid: str, skills: list[str], years: int) -> ExtractedCandidate:
    return ExtractedCandidate(
        name=f"{name}_{uid[:8]}",
        email=f"{name.lower()}_{uid}@test.com",
        phone="13800138000",
        summary=f"{years}年 {skills[0]} 开发",
        skills=skills,
        experience_years=years,
        education="本科",
        current_company="Acme",
        current_title="Engineer",
    )


@pytest_asyncio.fixture
async def e2e_client():
    async def _mock_user_id() -> str:
        return "test-user-id"

    async def _mock_org_scoped_db():
        from app.core.database import get_db as _get_db
        gen = _get_db()
        try:
            real_db = await gen.__anext__()
            yield OrgContext(org_id="test-org-id", user_id="test-user-id", role="hr"), real_db
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

    app.dependency_overrides[get_current_user_id] = _mock_user_id
    app.dependency_overrides[org_scoped_db] = _mock_org_scoped_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)
        app.dependency_overrides.pop(org_scoped_db, None)
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_search_candidates_skills_filter_real_works(e2e_client):
    """v1.1.1 核心: 验 skills filter 真生效, 不是 dead param.

    流程: 创建 2 candidate (1 个含 Python, 1 个含 Go) → 搜 skills=[Python] →
    只返 Python 那个, total=1.
    """
    py_id = uuid.uuid4().hex
    go_id = uuid.uuid4().hex

    files = {"file": ("r.txt", PYTHON_TEXT.encode(), "text/plain")}
    r = await e2e_client.post("/api/v1/resume/upload-resume", files=files)
    plain_py = r.json()["plain_text"]

    files = {"file": ("r2.txt", GO_TEXT.encode(), "text/plain")}
    r = await e2e_client.post("/api/v1/resume/upload-resume", files=files)
    plain_go = r.json()["plain_text"]

    with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
        mock_extract.side_effect = [
            _ext("张三", py_id, ["Python", "FastAPI"], 5),
            _ext("李四", go_id, ["Go", "Kubernetes"], 3),
        ]
        py_result = await resume_handlers["parse_resume"](content=plain_py, auto_create=True)
        go_result = await resume_handlers["parse_resume"](content=plain_go, auto_create=True)
    assert py_result["status"] == "success"
    assert go_result["status"] == "success"
    py_candidate_id = py_result["data"]["candidate_id"]
    go_candidate_id = go_result["data"]["candidate_id"]

    result = await search_handlers["search_candidates"](skills=["Python"], limit=50)
    assert "items" in result
    candidate_ids = {item["candidate_id"] for item in result["items"]}
    assert py_candidate_id in candidate_ids, f"Python candidate missing: {candidate_ids}"
    assert go_candidate_id not in candidate_ids, f"Go candidate leaked: {candidate_ids}"
    assert result["total"] >= 1

    result_go = await search_handlers["search_candidates"](skills=["Go"], limit=50)
    candidate_ids_go = {item["candidate_id"] for item in result_go["items"]}
    assert go_candidate_id in candidate_ids_go
    assert py_candidate_id not in candidate_ids_go

    result_both = await search_handlers["search_candidates"](skills=["Python", "Go"], limit=50)
    candidate_ids_both = {item["candidate_id"] for item in result_both["items"]}
    assert py_candidate_id in candidate_ids_both
    assert go_candidate_id in candidate_ids_both
