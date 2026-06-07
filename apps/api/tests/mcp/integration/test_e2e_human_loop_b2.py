"""Phase B · B2 AI Agent E2E — Human-in-loop 业务 orchestrator + ApprovalService 集成.

Momus §5.2: B2 = AI Agent E2E (Orchestrator mock LLM + 真 DB, 1.5d)
Phase B 修正版 (本次): 跳 A3+A4 已覆盖的 4 阶段 dispatch, 专注 Human-in-loop + ApprovalService 新视角.

覆盖 3 测:
  test_approval_service_create_resolve_lifecycle: 验 ApprovalService DB 持久化 (create → pending → resolve → approved/rejected)
  test_screening_agent_returns_needs_human_review: mock LLM 返低分, 验 ScreeningAgent.screen() 返 needs_human_review=True
  test_screening_to_approval_e2e: 端到端 — ScreeningAgent.screen() 返 needs_human_review → ApprovalService.create → resolve

设计原则 (复用 A3+A4+B1 模式):
  - mock LLM 在 app.agents.screening_agent.get_llm_client 入口 patch (B1 教训: patch module 内部 import 名字, 不是源头)
  - DB 真跑, ApprovalService 真实持久化
  - 不动 production code
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal, engine
from app.core.dependencies import get_current_user_id
from app.core.org_context import OrgContext, org_scoped_db
from app.main import app
from app.models.approval import Approval, ApprovalStatus


@pytest_asyncio.fixture
async def e2e_client():
    """复用 A3+A4+B1 fixture: AsyncClient + mock auth + org context.

    B2 增强: approvals FK 到 users, 测 e2e-tester@test.com (已 SQL 改 role=ADMIN, DB 里存在).
    """
    from app.core.security import create_access_token

    # 用 e2e-tester (DB 已存在, 之前 SQL 改 role=ADMIN 保留)
    real_user_id = "1d20462f-6dec-4be0-a48b-7595b3bf2ffb"  # e2e-tester user id

    async def _mock_user_id() -> str:
        return real_user_id

    async def _mock_org_scoped_db():
        from app.core.database import get_db as _get_db
        gen = _get_db()
        try:
            real_db = await gen.__anext__()
            yield OrgContext(org_id="test-org-id", user_id=real_user_id, role="hr"), real_db
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
async def test_approval_service_create_resolve_lifecycle(e2e_client):
    """B2 测 1: ApprovalService 端到端 — create → pending → resolve → approved."""
    from app.services.approval_service import ApprovalService

    unique_id = uuid.uuid4().hex[:8]

    # 1. create approval (pending)
    async with AsyncSessionLocal() as db:
        service = ApprovalService(db)
        approval = await service.create(
            user_id="1d20462f-6dec-4be0-a48b-7595b3bf2ffb",
            action_type="screening_approval",
            proposal={"summary": f"Test approval {unique_id}", "match_score": 4.5},
            target_type="candidate",
            target_id=f"cand-{unique_id}",
            candidate_email=f"test_{unique_id}@example.com",
        )
        approval_id = approval.id
        assert approval.status == ApprovalStatus.PENDING
        assert approval.action_type == "screening_approval"

    # 2. resolve (approved)
    async with AsyncSessionLocal() as db:
        service = ApprovalService(db)
        resolved = await service.resolve(
            approval_id=approval_id,
            resolver_id="resolver-user-id",
            approved=True,
            resolution="人工复审通过",
        )
        assert resolved is not None
        assert resolved.status == ApprovalStatus.APPROVED
        assert resolved.resolver_id == "resolver-user-id"
        assert resolved.resolution == "人工复审通过"
        assert resolved.resolved_at is not None

    # 3. 二次 resolve 应该返 None (PENDING 已被 resolve, 不再 PENDING)
    async with AsyncSessionLocal() as db:
        service = ApprovalService(db)
        again = await service.resolve(
            approval_id=approval_id,
            resolver_id="another-user",
            approved=False,
        )
        assert again is None, "二次 resolve 已 resolved approval 应返 None"

    # 4. DB 验证: approval 状态是 APPROVED
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Approval).where(Approval.id == approval_id))
        approval = result.scalar_one()
        assert approval.status == ApprovalStatus.APPROVED
        # cleanup (test org 用 test-org-id, 留存无害, 但 approval 数量累积需控制)
        # 暂不删, 测 cleanup 用 expire_pending() 或后续 PR 处理


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_screening_agent_returns_needs_human_review(e2e_client):
    """B2 测 2: mock LLM 返低分 (overall_score < 6), 验 ScreeningAgent.screen() 返 needs_human_review=True.

    复 B1 教训: patch app.agents.screening_agent.get_llm_client 入口 (module 内部 import 名字).
    """
    from app.agents.screening_agent import ScreeningAgent

    # mock LLM 返 low-score screening 结果
    low_score_llm_output = json.dumps({
        "parsed_resume": {
            "name": "李四",
            "email": "lisi@test.com",
            "skills": ["Java"],
            "experience_years": 2,
        },
        "match": {
            "overall_score": 3.5,
            "recommendation": "不推荐",
        },
        "gate": {
            "gate_passed": False,
            "score_adjusted": 3.0,
            "issues": ["经验不足 2年", "技能匹配低"],
            "needs_human_review": True,
            "gate_summary": "初筛不通过, 建议人工复审",
        },
    })

    fake_llm_client = MagicMock()
    fake_llm_client.chat = AsyncMock(return_value=low_score_llm_output)

    agent = ScreeningAgent()
    with patch("app.agents.screening_agent.get_llm_client", return_value=fake_llm_client):
        result = await agent.screen(
            candidate_id="cand-lisi",
            job_id="job-py-senior",
            resume_text="李四 2年 Java ...",
            job_requirements="5+ years Python, FastAPI 经验",
        )

    # 验 needs_human_review=True (业务关键决策)
    assert result["needs_human_review"] is True
    assert result["gate_passed"] is False
    # overall_score 来自 match.overall_score (不是 gate.score_adjusted, 见 screening_agent.py:222)
    assert result["overall_score"] == 3.5
    assert "经验不足" in result["summary"] or "建议人工" in result["summary"]


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_screening_to_approval_e2e(e2e_client):
    """B2 测 3: 端到端 — ScreeningAgent.screen 返 needs_human_review → 业务调 ApprovalService.create → resolve.

    测业务流: 当 LLM 返 needs_human_review, 业务应自动创建 approval (持久化), 人类 resolve.
    """
    from app.agents.screening_agent import ScreeningAgent
    from app.services.approval_service import ApprovalService

    unique_id = uuid.uuid4().hex[:8]
    low_score_llm_output = json.dumps({
        "parsed_resume": {
            "name": "王五",
            "email": f"wangwu_{unique_id}@test.com",
            "skills": ["PHP"],
            "experience_years": 1,
        },
        "match": {
            "overall_score": 2.5,
            "recommendation": "不推荐",
        },
        "gate": {
            "gate_passed": False,
            "score_adjusted": 2.0,
            "issues": ["经验严重不足"],
            "needs_human_review": True,
            "gate_summary": "建议人工复审",
        },
    })

    fake_llm_client = MagicMock()
    fake_llm_client.chat = AsyncMock(return_value=low_score_llm_output)

    agent = ScreeningAgent()
    with patch("app.agents.screening_agent.get_llm_client", return_value=fake_llm_client):
        screen_result = await agent.screen(
            candidate_id=f"cand-wangwu-{unique_id}",
            job_id=f"job-py-{unique_id}",
            resume_text="王五 1年 PHP",
            job_requirements="5+ years Python",
        )

    # 验 screening 返 needs_human_review=True
    assert screen_result["needs_human_review"] is True

    # 业务流: 当 needs_human_review=True 时, 调 ApprovalService.create 持久化审批
    if screen_result["needs_human_review"]:
        async with AsyncSessionLocal() as db:
            service = ApprovalService(db)
            approval = await service.create(
                user_id="1d20462f-6dec-4be0-a48b-7595b3bf2ffb",
                action_type="screening_approval",
                proposal={
                    "summary": f"自动创建 (match_score={screen_result['overall_score']})",
                    "match_score": screen_result["overall_score"],
                    "issues": screen_result.get("risks", []),
                },
                target_type="candidate",
                target_id=screen_result["candidate_id"],
                candidate_email=f"wangwu_{unique_id}@test.com",
            )
            assert approval.status == ApprovalStatus.PENDING
            approval_id = approval.id

        # 人类 (resolver) 复审通过
        async with AsyncSessionLocal() as db:
            service = ApprovalService(db)
            resolved = await service.resolve(
                approval_id=approval_id,
                resolver_id="hr-user-id",
                approved=True,
                resolution="人工复审通过, 接受候选人 (背景特殊)",
            )
            assert resolved.status == ApprovalStatus.APPROVED
            assert resolved.resolver_id == "hr-user-id"

    # 验 list_pending 不再含此 approval
    async with AsyncSessionLocal() as db:
        service = ApprovalService(db)
        pending = await service.list_pending(user_id="1d20462f-6dec-4be0-a48b-7595b3bf2ffb")
        pending_ids = [p["id"] for p in pending]
        assert approval_id not in pending_ids, f"resolved approval {approval_id} 仍 in pending"
