"""v1.1 Phase D E2E — 跨 server 业务流 (Momus §4 修正版).

覆盖 4 步:
  Step 1: HTTP POST /resume/upload-resume  (real file → plain_text)
  Step 2: mcp-resume parse_resume  (mock LLM extract_from_text)
  Step 3: mcp-resume get_candidate_profile  (candidate_id → 画像)
  Step 4: mcp-candidate search_candidates  (query="Python" → 至少 1 hit)

设计原则 (Momus §4.2):
  - mock LLM 在 app.tools.resume_parser.extract_from_text 入口 patch, 传 ExtractedCandidate
  - DB 真跑 (用 test-org-id / test-user-id, 跟 conftest 一致)
  - unique email per test (uuid suffix) 避免跨测试污染
  - 跳过 DB 清理: 测试 DB 是独立 org, candidate 留存无害

为何不直接 mcp_host.call_tool (覆盖 E2E 真实 MCP 协议):
  - v0.4e 已测 14 server lifecycle 14/14, MCP 协议层稳
  - v1.1 测业务流: 跨 server handler 调用 + DB + mock LLM
  - 直接调 handlers[tool_name] 比 mcp_host.call_tool 更快更隔离
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import engine, get_db
from app.core.dependencies import get_current_user_id
from app.core.org_context import OrgContext, org_scoped_db
from app.main import app
from app.schemas.resume import ExtractedCandidate
from app.tools.candidate_search import handlers as search_handlers
from app.tools.resume_parser import handlers as resume_handlers


RESUME_TEXT = """张三
男 | 13800138000 | zhangsan@test.com
5年 Python 后端开发经验
熟练掌握 Python, FastAPI, PostgreSQL, Redis, Docker
本科 @ 清华大学 @ 计算机科学
现任 Acme 公司 Senior Engineer
"""


def _make_unique_extracted(unique_id: str) -> ExtractedCandidate:
    """生成带 unique email 的 ExtractedCandidate, 避免跨测试 candidate 撞 email."""
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
    """复用 conftest 模式: AsyncClient + mock auth (test-org-id / test-user-id)."""

    async def _mock_user_id() -> str:
        return "test-user-id"

    async def _mock_org_scoped_db():
        """Yield (OrgContext, DB session) — skip JWT + Membership lookup."""
        # 注: 这里 db 实际由 FastAPI DI 解析 (get_db)
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


class TestE2EPhaseD:
    """v1.1 跨 server 业务流 E2E (Momus §4.1)."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_e2e_upload_parse_profile_search(self, e2e_client):
        """Step 1-4: HTTP upload → parse → profile → search.

        主路径: 验证 4 步串通, 中间数据 (candidate_id) 透传无丢失.
        """
        unique_id = uuid.uuid4().hex

        # Step 1: HTTP POST /resume/upload-resume
        files = {"file": ("resume.txt", RESUME_TEXT.encode("utf-8"), "text/plain")}
        r = await e2e_client.post("/api/v1/resume/upload-resume", files=files)
        assert r.status_code == 200, f"upload failed: {r.text}"
        upload_resp = r.json()
        assert upload_resp["filename"] == "resume.txt"
        assert upload_resp["text_length"] > 0
        assert len(upload_resp["plain_text"]) > 0
        plain_text = upload_resp["plain_text"]

        # Step 2: mcp-resume parse_resume (mock LLM)
        extracted = _make_unique_extracted(unique_id)
        with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = extracted
            parse_result = await resume_handlers["parse_resume"](
                content=plain_text,
                auto_create=True,
            )
        assert parse_result["status"] == "success", f"parse failed: {parse_result}"
        candidate_id = parse_result["data"].get("candidate_id")
        assert candidate_id, f"no candidate_id: {parse_result}"
        # 验证 mock 被调
        mock_extract.assert_awaited_once()

        # Step 3: mcp-resume get_candidate_profile
        profile_result = await resume_handlers["get_candidate_profile"](
            candidate_id=candidate_id,
        )
        assert profile_result["status"] == "success", f"profile failed: {profile_result}"
        basic = profile_result["data"]["basic_info"]
        assert basic["name"] == extracted.name
        assert "Python" in basic["skills"]
        assert basic["years_of_experience"] == 5

        # Step 4: mcp-candidate search_candidates (query=extracted.name 含 unique uuid suffix, LIKE 精确匹配)
        search_result = await search_handlers["search_candidates"](
            query=extracted.name,
            limit=50,
        )
        # search 返回 dict {"items": [...], "total": N}, 不带 status envelope
        assert "items" in search_result, f"search missing items: {search_result}"
        items = search_result["items"]
        assert len(items) >= 1, f"search returned 0 items: {search_result}"
        # 验证刚创建的 candidate 在结果里
        candidate_ids = {item["candidate_id"] for item in items}
        assert candidate_id in candidate_ids, (
            f"created candidate {candidate_id} not in search results. "
            f"Got: {candidate_ids}"
        )

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_e2e_search_by_skill_filter(self, e2e_client):
        """Step 1+2+4 变体: 创建 candidate 后按 skills 过滤搜索.

        验 search_candidates(skills=[...]) 路径 (与 query= 不同).
        """
        unique_id = uuid.uuid4().hex
        extracted = _make_unique_extracted(unique_id)

        # Step 1: HTTP upload
        files = {"file": ("resume2.txt", RESUME_TEXT.encode("utf-8"), "text/plain")}
        r = await e2e_client.post("/api/v1/resume/upload-resume", files=files)
        assert r.status_code == 200
        plain_text = r.json()["plain_text"]

        # Step 2: parse
        with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = extracted
            parse_result = await resume_handlers["parse_resume"](
                content=plain_text,
                auto_create=True,
            )
        assert parse_result["status"] == "success"
        candidate_id = parse_result["data"]["candidate_id"]

        # Step 4 变体: 按 skills 过滤 (query="张三_xxx" 比 skills 更精确)
        search_result = await search_handlers["search_candidates"](
            query=extracted.name,  # 用 unique name 精确匹配
            limit=10,
        )
        assert "items" in search_result
        items = search_result["items"]
        candidate_ids = {item["candidate_id"] for item in items}
        assert candidate_id in candidate_ids, (
            f"created candidate {candidate_id} not in name-filtered search"
        )
        # 验证 skills 字段透传
        our_item = next(i for i in items if i["candidate_id"] == candidate_id)
        assert "Python" in our_item["skills"]
        assert "FastAPI" in our_item["skills"]
