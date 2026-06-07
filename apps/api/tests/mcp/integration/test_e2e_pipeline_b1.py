"""Phase B · B1 AI Agent E2E — Pipeline (mock LLM) 端到端.

Momus §2.1 修正版:
  仿 v1.1+v1.2 模式, mock LLM 入口, 加 3 测 (每组件 1 测). 真 LLM E2E 推 Phase E.

覆盖 3 测:
  test_pipeline_build_screening: 验 build_screening_pipeline() 创建 3 步 pipeline
  test_pipeline_run_3_steps_with_mocked_llm: mock llm_chat_with_retry 返 3 个不同 JSON, 验 3 步全跑 + final_output 含 parsed_resume + match_result + gate_result
  test_pipeline_gate_failed_triggers_human_review: mock LLM 返 gate_passed=false, 验 needs_human_review=True

设计原则 (复用 A3+A4 模式):
  - mock LLM 在 app.llm.retry.llm_chat_with_retry 入口 patch
  - DB 真跑, unique email 避免污染 (虽然 Pipeline 不写 DB, 但 fixture 模式保持一致)
  - 不动 production code
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import engine
from app.core.dependencies import get_current_user_id
from app.core.org_context import OrgContext, org_scoped_db
from app.main import app


@pytest_asyncio.fixture
async def e2e_client():
    """复用 A3+A4 fixture: AsyncClient + mock auth + org context."""

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
@pytest.mark.timeout(30)
async def test_pipeline_build_screening(e2e_client):
    """B1 测 1: build_screening_pipeline() 工厂方法创建 3 步 pipeline."""
    from app.agents.pipeline import PipelineAgent

    pipeline = PipelineAgent.build_screening_pipeline()
    assert pipeline.name == "resume_screening"
    assert len(pipeline.steps) == 3
    step_names = [step.name for step in pipeline.steps]
    assert step_names == ["parse", "match", "gate"]


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_pipeline_run_3_steps_with_mocked_llm(e2e_client):
    """B1 测 2: mock LLM client 入口, 3 步端到端, 验 final_output 含 3 步结果.

    mock app.llm.get_llm_client 返 fake LLM client, 它的 .chat() mock 返 3 个不同 JSON.
    比 patch llm_chat_with_retry 入口更深 (后者 mock 失败: 测试时 LLM 仍真打 omlx 502,
    可能 retry.py 内部对 mock 处理有 quirk, mock get_llm_client 更稳).
    """
    from app.agents.pipeline import PipelineAgent

    parse_response = json.dumps({
        "name": "张三",
        "email": "zhangsan@test.com",
        "phone": "13800138000",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "experience_years": 5,
        "education": {"degree": "本科", "major": "CS", "school": "清华"},
        "recent_roles": ["Senior Engineer @ Acme"],
        "key_achievements": ["FastAPI 重构, QPS +200%"],
    })
    match_response = json.dumps({
        "skills_match": {"score": 9, "matched": ["Python", "FastAPI"], "missing": []},
        "experience_match": {"score": 8, "analysis": "5年经验匹配"},
        "education_match": {"score": 9, "analysis": "本科 CS 匹配"},
        "overall_score": 8.7,
        "strengths": ["FastAPI 经验扎实"],
        "weaknesses": [],
        "recommendation": "强烈推荐",
    })
    gate_response = json.dumps({
        "gate_passed": True,
        "score_adjusted": 8.5,
        "issues": [],
        "needs_human_review": False,
        "gate_summary": "质检通过, 无问题",
    })

    fake_llm_client = MagicMock()
    fake_llm_client.chat = AsyncMock(side_effect=[parse_response, match_response, gate_response])

    pipeline = PipelineAgent.build_screening_pipeline()
    with patch("app.agents.pipeline.get_llm_client", return_value=fake_llm_client):
        result = await pipeline.run({
            "resume_text": "张三 5年 Python FastAPI ...",
            "job_requirements": "5+ years Python, FastAPI 经验",
        })

    # 验 pipeline 整体结果
    assert result["status"] == "completed"
    assert result["agent"] == "resume_screening"
    assert "pipeline_id" in result
    assert len(result["steps"]) == 3

    # 验 3 步全部 completed
    step_names = [s["step"] for s in result["steps"]]
    assert step_names == ["parse", "match", "gate"]
    for step in result["steps"]:
        assert step["status"] == "completed"

    # 验 final_output 含 3 步的 context 累积结果
    final = result["final_output"]
    assert final["parsed_resume"]["name"] == "张三"
    assert final["parsed_resume"]["skills"] == ["Python", "FastAPI", "PostgreSQL"]
    assert final["match_result"]["overall_score"] == 8.7
    assert final["match_result"]["recommendation"] == "强烈推荐"
    assert final["gate_result"]["gate_passed"] is True
    assert final["gate_result"]["gate_summary"] == "质检通过, 无问题"
    assert final["final_score"] == 8.5
    assert final["gate_passed"] is True
    assert final["needs_human_review"] is False

    # 验 mock LLM 被调 3 次
    assert fake_llm_client.chat.call_count == 3


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_pipeline_gate_failed_triggers_human_review(e2e_client):
    """B1 测 3: gate_passed=false + needs_human_review=true 路径, 验 Pipeline 不阻断但标记人工复审."""
    from app.agents.pipeline import PipelineAgent

    parse_response = json.dumps({
        "name": "李四",
        "email": "lisi@test.com",
        "skills": ["Java"],
        "experience_years": 2,
    })
    match_response = json.dumps({
        "overall_score": 3.5,  # 低于 6
        "recommendation": "不推荐",
    })
    gate_response = json.dumps({
        "gate_passed": False,
        "score_adjusted": 3.0,
        "issues": ["经验不足", "技能匹配低"],
        "needs_human_review": True,
        "gate_summary": "质检不通过, 建议人工复审",
    })

    fake_llm_client = MagicMock()
    fake_llm_client.chat = AsyncMock(side_effect=[parse_response, match_response, gate_response])

    pipeline = PipelineAgent.build_screening_pipeline()
    with patch("app.agents.pipeline.get_llm_client", return_value=fake_llm_client):
        result = await pipeline.run({
            "resume_text": "李四 2年 Java ...",
            "job_requirements": "5+ years Python",
        })

    # 验 gate 失败路径
    final = result["final_output"]
    assert final["gate_result"]["gate_passed"] is False
    assert final["gate_result"]["needs_human_review"] is True
    assert final["gate_passed"] is False  # pipeline 标记未通过
    assert final["needs_human_review"] is True  # pipeline 标记需人工复审
    assert "经验不足" in final["gate_result"]["issues"]
    assert final["final_score"] == 3.0
