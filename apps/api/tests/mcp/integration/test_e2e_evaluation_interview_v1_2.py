"""v1.2 跨 Server 业务流 E2E — candidate → job → interview → evaluation → report.

覆盖 5 步 (Momus §3 关注点):
  Step 1: HTTP upload + mcp-resume parse_resume (mock LLM) → candidate_id
  Step 2: mcp-job create_job → job_id
  Step 3: mcp-interview schedule_interview → interview_id
  Step 4: mcp-evaluation save_evaluation (R1, score 8.5, strong_hire) → evaluation_id
  Step 5: mcp-evaluation generate_evaluation_report → 含 R1 评估的汇总

设计原则 (复用 v1.1):
  - mock LLM 在 app.tools.resume_parser.extract_from_text 入口 patch
  - DB 真跑, unique email 避免污染
  - 不动 production code
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
from app.tools.application import handlers as application_handlers
from app.tools.evaluation import handlers as evaluation_handlers
from app.tools.interview import handlers as interview_handlers
from app.tools.job import handlers as job_handlers
from app.tools.resume_parser import handlers as resume_handlers


RESUME_TEXT = """张三
男 | 13800138000 | zhangsan@test.com
5年 Python 后端开发经验
熟练掌握 Python, FastAPI, PostgreSQL, Redis, Docker
本科 @ 清华大学 @ 计算机科学
现任 Acme 公司 Senior Engineer
"""


def _make_extracted(unique_id: str) -> ExtractedCandidate:
    return ExtractedCandidate(
        name=f"张三_{unique_id[:8]}",
        email=f"z_{unique_id}@test.com",
        phone="13800138000",
        summary="5年 Python 后端开发经验",
        skills=["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"],
        experience_years=5,
        education="本科 @ 清华大学 @ 计算机科学",
        current_company="Acme",
        current_title="Senior Engineer",
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
async def test_e2e_candidate_interview_evaluation_flow(e2e_client):
    """v1.2 主路径: candidate → job → interview → evaluation → report 跨 3 server E2E."""
    unique_id = uuid.uuid4().hex
    extracted = _make_extracted(unique_id)

    files = {"file": ("r.txt", RESUME_TEXT.encode(), "text/plain")}
    r = await e2e_client.post("/api/v1/resume/upload-resume", files=files)
    assert r.status_code == 200, f"upload failed: {r.text}"
    plain_text = r.json()["plain_text"]

    with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = extracted
        parse_result = await resume_handlers["parse_resume"](content=plain_text, auto_create=True)
    assert parse_result["status"] == "success", f"parse failed: {parse_result}"
    candidate_id = parse_result["data"]["candidate_id"]
    assert candidate_id

    job_result = await job_handlers["create_job"](
        title="Senior Python Engineer",
        department="Engineering",
        location="Shanghai",
        description="Backend dev with FastAPI experience",
        requirements="5+ years Python",
        salary_range="40-60K",
        status="active",
    )
    assert job_result["status"] == "success", f"create_job failed: {job_result}"
    job_id = job_result["data"]["job_id"]
    assert job_id

    app_result = await application_handlers["create_application"](
        candidate_id=candidate_id,
        job_id=job_id,
        resume_url="",
    )
    assert app_result["status"] == "success", f"create_application failed: {app_result}"
    application_id = app_result["data"]["application_id"]
    assert application_id

    interview_result = await interview_handlers["schedule_interview"](
        candidate_id=candidate_id,
        job_id=job_id,
        scheduled_time="2026-07-01T10:00:00+08:00",
        notes="视频面试 R1",
        application_id=application_id,
    )
    assert interview_result["status"] == "scheduled", f"schedule failed: {interview_result}"
    interview_id = interview_result["id"]
    assert interview_id

    eval_result = await evaluation_handlers["save_evaluation"](
        interview_id=interview_id,
        round="R1",
        overall_score=8.5,
        verdict="strong_hire",
        dimensions={"技术": 9, "沟通": 8},
        key_observations="扎实的 FastAPI 经验, 系统设计能力强",
        feedback="强烈推荐",
    )
    assert eval_result["status"] == "success", f"save_evaluation failed: {eval_result}"
    evaluation_id = eval_result["data"]["evaluation_id"]
    assert evaluation_id

    report_result = await evaluation_handlers["generate_evaluation_report"](
        candidate_id=candidate_id,
    )
    assert report_result["status"] == "success", f"report failed: {report_result}"
    data = report_result["data"]
    assert data["candidate_id"] == candidate_id
    assert data["total_interviews"] == 1
    assert len(data["rounds"]) == 1
    r1 = data["rounds"][0]
    assert r1["round"] == "phone_screen"  # InterviewRound.R1 enum value (model 定义)
    assert r1["overall_score"] == 8.5
    assert r1["verdict"] == "strong_hire"
    assert data["average_score"] == 8.5
    assert data["overall_verdict"] == "strong_hire"
