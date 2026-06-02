"""Tests for app/api/conversation.py — Session & message management + screen chat.

覆盖 create/list/get/delete/update session、get_messages、screen_chat
以及 404 路径、LLM 失败回退、历史消息过滤。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.conversation import router as conversation_router
from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.models.candidate import Candidate
from app.models.job_position import JobPosition


# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def fake_user_id() -> str:
    return "user-1"


@pytest.fixture
def app(fake_user_id: str) -> FastAPI:
    app = FastAPI()
    app.include_router(conversation_router, prefix="/conversation")
    app.dependency_overrides[get_current_user_id] = lambda: fake_user_id
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _patch_db(app: FastAPI, db_mock):
    async def fake_get_db():
        yield db_mock

    app.dependency_overrides[get_db] = fake_get_db


def _make_session(
    id: str = "sess-1",
    user_id: str = "user-1",
    title: str = "新对话",
    session_metadata: dict | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = id
    s.user_id = user_id
    s.title = title
    s.session_metadata = session_metadata
    s.created_at = created_at or datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
    s.updated_at = updated_at or datetime(2026, 6, 2, 13, 0, 0, tzinfo=timezone.utc)
    return s


def _make_message(
    id: str = "msg-1",
    role: str = "user",
    content: str = "hello",
    tool_calls: list | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = id
    m.role = role
    m.content = content
    m.tool_calls = tool_calls
    m.created_at = created_at or datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
    return m


# ─── create_session (POST /conversation/session) ──────────────────────


class TestCreateSession:
    def test_success(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        new_sess = _make_session(id="new-sess", title="招聘评估")

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.create_session = AsyncMock(return_value=new_sess)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).post(
                "/conversation/session", json={"title": "招聘评估"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "new-sess"
        assert body["title"] == "招聘评估"
        assert body["created_at"] == "2026-06-02T12:00:00+00:00"

    def test_default_title(self, app: FastAPI) -> None:
        """不传 title → 默认 '新对话'."""
        db = MagicMock()
        _patch_db(app, db)
        new_sess = _make_session(title="新对话")

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.create_session = AsyncMock(return_value=new_sess)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).post("/conversation/session", json={})

        assert resp.status_code == 200
        assert resp.json()["title"] == "新对话"
        # 验证 default title 透传到 service
        call = mock_svc.create_session.call_args
        assert call.kwargs.get("title") == "新对话"

    def test_null_metadata_returns_empty_dict(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        new_sess = _make_session(session_metadata=None)

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.create_session = AsyncMock(return_value=new_sess)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).post("/conversation/session", json={})

        assert resp.json()["metadata"] == {}


# ─── list_sessions (GET /conversation/sessions) ───────────────────────


class TestListSessions:
    def test_success(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        s1 = _make_session(id="s1", title="会话1")
        s2 = _make_session(id="s2", title="会话2")

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.list_sessions = AsyncMock(return_value=[s1, s2])
            mock_svc.get_session_message_count = AsyncMock(side_effect=[3, 7])
            MockSvc.return_value = mock_svc
            resp = TestClient(app).get(
                "/conversation/sessions", params={"limit": 20, "offset": 0}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["sessions"]) == 2
        assert body["sessions"][0]["id"] == "s1"
        assert body["sessions"][0]["message_count"] == 3
        assert body["sessions"][1]["id"] == "s2"
        assert body["sessions"][1]["message_count"] == 7

    def test_empty_list(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.list_sessions = AsyncMock(return_value=[])
            MockSvc.return_value = mock_svc
            resp = TestClient(app).get("/conversation/sessions")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["sessions"] == []


# ─── get_session (GET /conversation/session/{id}) ─────────────────────


class TestGetSession:
    def test_success(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        sess = _make_session(id="s1", title="测试")

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_session_message_count = AsyncMock(return_value=5)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).get("/conversation/session/s1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "s1"
        assert body["title"] == "测试"
        assert body["message_count"] == 5

    def test_not_found(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=None)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).get("/conversation/session/missing")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "会话不存在"

    def test_other_user_session_forbidden(self, app: FastAPI, fake_user_id: str) -> None:
        """其他用户的 session → 404 (不泄漏存在性)."""
        db = MagicMock()
        _patch_db(app, db)
        other_sess = _make_session(id="s1", user_id="other-user")

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=other_sess)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).get("/conversation/session/s1")

        assert resp.status_code == 404


# ─── delete_session (DELETE /conversation/session/{id}) ──────────────


class TestDeleteSession:
    def test_success(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        sess = _make_session(id="s1")

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.delete_session = AsyncMock(return_value=True)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).delete("/conversation/session/s1")

        assert resp.status_code == 200
        assert resp.json()["message"] == "已删除"
        # 验证 service.delete_session 被调用
        mock_svc.delete_session.assert_awaited_once_with("s1")

    def test_not_found(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=None)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).delete("/conversation/session/missing")

        assert resp.status_code == 404


# ─── update_session (PATCH /conversation/session/{id}) ───────────────


class TestUpdateSession:
    def test_update_title_only(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        original = _make_session(id="s1", title="旧标题")
        updated = _make_session(id="s1", title="新标题")

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=original)
            mock_svc.update_session_title = AsyncMock(return_value=updated)
            mock_svc.get_session_message_count = AsyncMock(return_value=2)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).patch(
                "/conversation/session/s1", json={"title": "新标题"}
            )

        assert resp.status_code == 200
        assert resp.json()["title"] == "新标题"
        mock_svc.update_session_title.assert_awaited_once_with("s1", "新标题")
        # metadata 没传 → 不应调用 update_session_metadata
        mock_svc.update_session_metadata.assert_not_called()

    def test_update_metadata_only(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        original = _make_session(id="s1", session_metadata={"a": 1})
        updated = _make_session(id="s1", session_metadata={"a": 1, "b": 2})

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=original)
            mock_svc.update_session_metadata = AsyncMock(return_value=updated)
            mock_svc.get_session_message_count = AsyncMock(return_value=2)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).patch(
                "/conversation/session/s1", json={"metadata": {"b": 2}}
            )

        assert resp.status_code == 200
        assert resp.json()["metadata"] == {"a": 1, "b": 2}
        mock_svc.update_session_metadata.assert_awaited_once_with("s1", {"b": 2})
        mock_svc.update_session_title.assert_not_called()

    def test_update_both(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        original = _make_session(id="s1", title="旧", session_metadata={"x": 1})
        updated = _make_session(id="s1", title="新", session_metadata={"x": 1, "y": 2})

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=original)
            mock_svc.update_session_title = AsyncMock(return_value=updated)
            mock_svc.update_session_metadata = AsyncMock(return_value=updated)
            mock_svc.get_session_message_count = AsyncMock(return_value=0)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).patch(
                "/conversation/session/s1",
                json={"title": "新", "metadata": {"y": 2}},
            )

        assert resp.status_code == 200
        # 两次更新都被调用
        mock_svc.update_session_title.assert_awaited_once()
        mock_svc.update_session_metadata.assert_awaited_once()

    def test_not_found(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=None)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).patch(
                "/conversation/session/missing", json={"title": "x"}
            )

        assert resp.status_code == 404


# ─── get_messages (GET /conversation/session/{id}/messages) ──────────


class TestGetMessages:
    def test_success(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        sess = _make_session(id="s1")
        msgs = [
            _make_message(id="m1", role="user", content="你好"),
            _make_message(id="m2", role="assistant", content="你好,我是AI"),
        ]

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_history = AsyncMock(return_value=msgs)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).get("/conversation/session/s1/messages")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][0]["content"] == "你好"
        assert body["messages"][1]["role"] == "assistant"

    def test_empty_history(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        sess = _make_session(id="s1")

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_history = AsyncMock(return_value=[])
            MockSvc.return_value = mock_svc
            resp = TestClient(app).get("/conversation/session/s1/messages")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["messages"] == []

    def test_passes_before_id(self, app: FastAPI) -> None:
        """before_id 透传给 service.get_history."""
        db = MagicMock()
        _patch_db(app, db)
        sess = _make_session(id="s1")

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_history = AsyncMock(return_value=[])
            MockSvc.return_value = mock_svc
            TestClient(app).get(
                "/conversation/session/s1/messages",
                params={"before_id": "m50", "limit": 10},
            )

        call = mock_svc.get_history.call_args
        assert call.kwargs.get("before_id") == "m50"
        assert call.kwargs.get("limit") == 10

    def test_message_with_tool_calls(self, app: FastAPI) -> None:
        """message.tool_calls → 序列化到响应."""
        db = MagicMock()
        _patch_db(app, db)
        sess = _make_session(id="s1")
        tool_calls = [{"name": "search", "args": {"q": "python"}}]
        msgs = [_make_message(id="m1", role="assistant", tool_calls=tool_calls)]

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_history = AsyncMock(return_value=msgs)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).get("/conversation/session/s1/messages")

        assert resp.json()["messages"][0]["tool_calls"] == tool_calls

    def test_not_found(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=None)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).get("/conversation/session/missing/messages")

        assert resp.status_code == 404


# ─── screen_chat (POST /conversation/session/{id}/screen) ───────────


def _make_candidate(
    id: str = "c1",
    name: str = "张三",
    skills: list | None = None,
    experience_years: int | None = 5,
    current_company: str | None = "ABC Corp",
    current_title: str | None = "工程师",
    education: str | None = "本科",
) -> MagicMock:
    c = MagicMock(spec=Candidate)
    c.id = id
    c.name = name
    c.skills = skills or ["Python", "FastAPI"]
    c.experience_years = experience_years
    c.current_company = current_company
    c.current_title = current_title
    c.education = education
    return c


def _make_job(
    id: str = "j1",
    title: str = "高级 Python 工程师",
    requirements: str = "5+年经验,熟悉 FastAPI",
) -> MagicMock:
    j = MagicMock(spec=JobPosition)
    j.id = id
    j.title = title
    j.requirements = requirements
    return j


class TestScreenChat:
    def _setup_db_with_candidate_and_job(self, app: FastAPI, candidate=None, job=None):
        """Setup db mock to return candidate and job from select queries."""
        db = MagicMock()

        # 第一次查询 (candidate) → 返回 candidate
        cand_result = MagicMock()
        cand_result.scalar_one_or_none = MagicMock(return_value=candidate or _make_candidate())
        # 第二次查询 (job) → 返回 job
        job_result = MagicMock()
        job_result.scalar_one_or_none = MagicMock(return_value=job or _make_job())

        db.execute = AsyncMock(side_effect=[cand_result, job_result])
        _patch_db(app, db)
        return db

    def test_success(self, app: FastAPI) -> None:
        candidate = _make_candidate()
        job = _make_job()
        sess = _make_session(id="s1")
        # 历史消息中 system 角色应被过滤
        history = [
            _make_message(id="h1", role="user", content="之前的提问"),
            _make_message(id="h2", role="assistant", content="之前的回答"),
            _make_message(id="h3", role="system", content="旧系统消息(应被过滤)"),
        ]
        db = self._setup_db_with_candidate_and_job(app, candidate, job)

        with patch("app.api.conversation.ConversationService") as MockSvc, \
             patch("app.api.conversation.get_llm_client") as mock_get_llm:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_last_n_messages = AsyncMock(return_value=history)
            mock_svc.add_message = AsyncMock(return_value=MagicMock())
            MockSvc.return_value = mock_svc
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value="候选人技术能力不错,推荐面试。")
            mock_get_llm.return_value = mock_llm

            resp = TestClient(app).post(
                "/conversation/session/s1/screen",
                json={
                    "session_id": "s1",
                    "message": "技术怎么样?",
                    "candidate_id": "c1",
                    "job_id": "j1",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["reply"] == "候选人技术能力不错,推荐面试。"
        assert body["session_id"] == "s1"

        # 验证 LLM 收到 messages: system prompt + 候选人上下文 + 2 条非 system 历史 + 用户消息
        llm_call = mock_llm.chat.call_args
        messages = llm_call.args[0]
        assert messages[0]["role"] == "system"  # SCREEN_CHAT_SYSTEM_PROMPT
        assert "AI招聘初筛助手" in messages[0]["content"]
        assert messages[1]["role"] == "system"  # 候选人上下文
        assert "张三" in messages[1]["content"]
        assert "Python" in messages[1]["content"]
        assert "ABC Corp" in messages[1]["content"]
        # 2 条历史消息(过滤掉 system 后)
        assert messages[2]["content"] == "之前的提问"
        assert messages[3]["content"] == "之前的回答"
        # 用户消息
        assert messages[4]["role"] == "user"
        assert messages[4]["content"] == "技术怎么样?"
        # 验证 temperature/max_tokens
        assert llm_call.kwargs["temperature"] == 0.3
        assert llm_call.kwargs["max_tokens"] == 2048

    def test_candidate_minimal_fields(self, app: FastAPI) -> None:
        """候选人缺少可选字段 → context 中应跳过这些行."""
        candidate = _make_candidate(
            name=None,
            skills=None,
            experience_years=None,
            current_company=None,
            current_title=None,
            education=None,
        )
        job = _make_job(requirements=None)
        sess = _make_session(id="s1")
        self._setup_db_with_candidate_and_job(app, candidate, job)

        with patch("app.api.conversation.ConversationService") as MockSvc, \
             patch("app.api.conversation.get_llm_client") as mock_get_llm:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_last_n_messages = AsyncMock(return_value=[])
            mock_svc.add_message = AsyncMock(return_value=MagicMock())
            MockSvc.return_value = mock_svc
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value="ok")
            mock_get_llm.return_value = mock_llm

            resp = TestClient(app).post(
                "/conversation/session/s1/screen",
                json={
                    "session_id": "s1",
                    "message": "x",
                    "candidate_id": "c1",
                    "job_id": "j1",
                },
            )

        assert resp.status_code == 200
        # 验证 context 中包含 "未知"
        context = mock_llm.chat.call_args.args[0][1]["content"]
        assert "未知" in context
        assert "高级 Python 工程师" in context
        # 不应包含 "当前公司/当前职位/学历"
        assert "当前公司" not in context
        assert "当前职位" not in context
        assert "学历" not in context

    def test_session_not_found(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        candidate = _make_candidate()
        job = _make_job()

        cand_result = MagicMock()
        cand_result.scalar_one_or_none = MagicMock(return_value=candidate)
        job_result = MagicMock()
        job_result.scalar_one_or_none = MagicMock(return_value=job)
        db.execute = AsyncMock(side_effect=[cand_result, job_result])

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=None)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).post(
                "/conversation/session/missing/screen",
                json={
                    "session_id": "missing",
                    "message": "x",
                    "candidate_id": "c1",
                    "job_id": "j1",
                },
            )

        assert resp.status_code == 404
        assert "会话不存在" in resp.json()["detail"]

    def test_candidate_not_found(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        sess = _make_session(id="s1")

        cand_result = MagicMock()
        cand_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=cand_result)

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).post(
                "/conversation/session/s1/screen",
                json={
                    "session_id": "s1",
                    "message": "x",
                    "candidate_id": "missing",
                    "job_id": "j1",
                },
            )

        assert resp.status_code == 404
        assert "候选人不存在" in resp.json()["detail"]

    def test_job_not_found(self, app: FastAPI) -> None:
        db = MagicMock()
        _patch_db(app, db)
        sess = _make_session(id="s1")
        candidate = _make_candidate()

        cand_result = MagicMock()
        cand_result.scalar_one_or_none = MagicMock(return_value=candidate)
        job_result = MagicMock()
        job_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(side_effect=[cand_result, job_result])

        with patch("app.api.conversation.ConversationService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            MockSvc.return_value = mock_svc
            resp = TestClient(app).post(
                "/conversation/session/s1/screen",
                json={
                    "session_id": "s1",
                    "message": "x",
                    "candidate_id": "c1",
                    "job_id": "missing",
                },
            )

        assert resp.status_code == 404
        assert "职位不存在" in resp.json()["detail"]

    def test_llm_failure_falls_back(self, app: FastAPI) -> None:
        """LLM 调用失败 → 返回兜底回复 + 仍记录两条消息."""
        candidate = _make_candidate()
        job = _make_job()
        sess = _make_session(id="s1")
        self._setup_db_with_candidate_and_job(app, candidate, job)

        with patch("app.api.conversation.ConversationService") as MockSvc, \
             patch("app.api.conversation.get_llm_client") as mock_get_llm:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_last_n_messages = AsyncMock(return_value=[])
            mock_svc.add_message = AsyncMock(return_value=MagicMock())
            MockSvc.return_value = mock_svc
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM 502"))
            mock_get_llm.return_value = mock_llm

            resp = TestClient(app).post(
                "/conversation/session/s1/screen",
                json={
                    "session_id": "s1",
                    "message": "x",
                    "candidate_id": "c1",
                    "job_id": "j1",
                },
            )

        assert resp.status_code == 200
        assert "无法完成评估" in resp.json()["reply"]
        # 仍调用 add_message 两次(用户消息 + 助手兜底消息)
        assert mock_svc.add_message.await_count == 2
        # 第二次调用应该是 assistant 角色
        second_call = mock_svc.add_message.call_args_list[1]
        assert second_call.args[2] == "assistant"
        assert "无法完成评估" in second_call.args[3]

    def test_saves_user_and_assistant_messages(self, app: FastAPI) -> None:
        """成功后 add_message 应被调用两次:user + assistant."""
        candidate = _make_candidate()
        job = _make_job()
        sess = _make_session(id="s1")
        self._setup_db_with_candidate_and_job(app, candidate, job)

        with patch("app.api.conversation.ConversationService") as MockSvc, \
             patch("app.api.conversation.get_llm_client") as mock_get_llm:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_last_n_messages = AsyncMock(return_value=[])
            mock_svc.add_message = AsyncMock(return_value=MagicMock())
            MockSvc.return_value = mock_svc
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value="AI 回复内容")
            mock_get_llm.return_value = mock_llm

            TestClient(app).post(
                "/conversation/session/s1/screen",
                json={
                    "session_id": "s1",
                    "message": "我的问题",
                    "candidate_id": "c1",
                    "job_id": "j1",
                },
            )

        assert mock_svc.add_message.await_count == 2
        # 第一次:user
        first = mock_svc.add_message.call_args_list[0]
        assert first.args[0] == "s1"
        assert first.args[1] == "user-1"
        assert first.args[2] == "user"
        assert first.args[3] == "我的问题"
        # 第二次:assistant
        second = mock_svc.add_message.call_args_list[1]
        assert second.args[2] == "assistant"
        assert second.args[3] == "AI 回复内容"

    def test_filters_system_messages_from_history(self, app: FastAPI) -> None:
        """历史中 system 角色消息应被过滤掉."""
        candidate = _make_candidate()
        job = _make_job()
        sess = _make_session(id="s1")
        history = [
            _make_message(id="s1", role="system", content="system-1"),
            _make_message(id="s2", role="system", content="system-2"),
            _make_message(id="u1", role="user", content="user-1"),
        ]
        self._setup_db_with_candidate_and_job(app, candidate, job)

        with patch("app.api.conversation.ConversationService") as MockSvc, \
             patch("app.api.conversation.get_llm_client") as mock_get_llm:
            mock_svc = AsyncMock()
            mock_svc.get_session = AsyncMock(return_value=sess)
            mock_svc.get_last_n_messages = AsyncMock(return_value=history)
            mock_svc.add_message = AsyncMock(return_value=MagicMock())
            MockSvc.return_value = mock_svc
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value="ok")
            mock_get_llm.return_value = mock_llm

            TestClient(app).post(
                "/conversation/session/s1/screen",
                json={
                    "session_id": "s1",
                    "message": "x",
                    "candidate_id": "c1",
                    "job_id": "j1",
                },
            )

        messages = mock_llm.chat.call_args.args[0]
        # system-1, system-2 被过滤,只保留 user-1
        history_msgs = [m for m in messages if m["role"] in ("user", "assistant") and m["content"] in ("user-1",)]
        assert len(history_msgs) == 1
        assert history_msgs[0]["content"] == "user-1"
        # 不应有 "system-1" 或 "system-2"
        all_content = " ".join(m["content"] for m in messages)
        assert "system-1" not in all_content
        assert "system-2" not in all_content

    def test_request_validation_empty_message(self, app: FastAPI) -> None:
        """message 为空 → 422 Pydantic 验证失败."""
        resp = TestClient(app).post(
            "/conversation/session/s1/screen",
            json={
                "session_id": "s1",
                "message": "",
                "candidate_id": "c1",
                "job_id": "j1",
            },
        )
        assert resp.status_code == 422
