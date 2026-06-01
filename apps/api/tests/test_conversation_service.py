"""Tests for ConversationService — session and message persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.conversation import ConversationMessage, ConversationSession
from app.services.conversation_service import ConversationService


def _mock_session(session_id: str = "s1", user_id: str = "u1") -> MagicMock:
    s = MagicMock(spec=ConversationSession)
    s.id = session_id
    s.user_id = user_id
    s.title = "测试对话"
    s.session_metadata = {}
    s.updated_at = datetime.now(timezone.utc)
    s.created_at = datetime.now(timezone.utc)
    return s


def _mock_message(
    msg_id: str = "m1",
    session_id: str = "s1",
    role: str = "user",
    content: str = "hello",
) -> MagicMock:
    m = MagicMock(spec=ConversationMessage)
    m.id = msg_id
    m.session_id = session_id
    m.user_id = "u1"
    m.role = role
    m.content = content
    m.tool_calls = None
    m.tool_result = None
    m.created_at = datetime.now(timezone.utc)
    return m


class TestConversationServiceCreateSession:
    @pytest.mark.asyncio
    async def test_create_session(self) -> None:
        db = AsyncMock()
        svc = ConversationService(db)
        result = await svc.create_session("u1", "我的对话")
        assert result.user_id == "u1"
        assert result.title == "我的对话"
        assert result.id is not None
        db.add.assert_called_once()
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_create_session_default_title(self) -> None:
        db = AsyncMock()
        svc = ConversationService(db)
        result = await svc.create_session("u1")
        assert result.title == "新对话"


class TestConversationServiceListSessions:
    @pytest.mark.asyncio
    async def test_list_sessions_returns_results(self) -> None:
        db = AsyncMock()
        s1 = _mock_session("s1", "u1")
        s2 = _mock_session("s2", "u1")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[s1, s2])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.list_sessions("u1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.list_sessions("u1")
        assert result == []


class TestConversationServiceGetSession:
    @pytest.mark.asyncio
    async def test_get_session_found(self) -> None:
        db = AsyncMock()
        session = _mock_session("s1", "u1")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.get_session("s1")
        assert result is not None
        assert result.id == "s1"

    @pytest.mark.asyncio
    async def test_get_session_not_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.get_session("nonexistent")
        assert result is None


class TestConversationServiceDeleteSession:
    @pytest.mark.asyncio
    async def test_delete_session_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.delete_session("s1")
        assert result is True
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.delete_session("nonexistent")
        assert result is False


class TestConversationServiceUpdateSession:
    @pytest.mark.asyncio
    async def test_update_session_metadata(self) -> None:
        db = AsyncMock()
        session = _mock_session("s1")
        session.session_metadata = {"key": "old"}
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.update_session_metadata("s1", {"key": "new", "extra": "val"})
        assert result is not None
        assert result.session_metadata["key"] == "new"
        assert result.session_metadata["extra"] == "val"

    @pytest.mark.asyncio
    async def test_update_session_metadata_not_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.update_session_metadata("nonexistent", {})
        assert result is None

    @pytest.mark.asyncio
    async def test_update_session_title(self) -> None:
        db = AsyncMock()
        session = _mock_session("s1")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.update_session_title("s1", "新标题")
        assert result is not None
        assert result.title == "新标题"

    @pytest.mark.asyncio
    async def test_update_session_title_not_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.update_session_title("nonexistent", "x")
        assert result is None


class TestConversationServiceAddMessage:
    @pytest.mark.asyncio
    async def test_add_message(self) -> None:
        db = AsyncMock()
        svc = ConversationService(db)
        result = await svc.add_message("s1", "u1", "user", "hello")
        assert result.session_id == "s1"
        assert result.role == "user"
        assert result.content == "hello"
        db.add.assert_called_once()
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_add_message_with_tool_calls(self) -> None:
        db = AsyncMock()
        svc = ConversationService(db)
        tool_calls = [{"id": "call_1", "function": {"name": "search", "arguments": "{}"}}]
        result = await svc.add_message("s1", "u1", "assistant", "found 3", tool_calls=tool_calls)
        assert result.tool_calls == tool_calls


class TestConversationServiceAddMessages:
    @pytest.mark.asyncio
    async def test_add_messages(self) -> None:
        db = AsyncMock()
        svc = ConversationService(db)
        messages = [
            {"session_id": "s1", "user_id": "u1", "role": "user", "content": "hi"},
            {"session_id": "s1", "user_id": "u1", "role": "assistant", "content": "hello"},
        ]
        result = await svc.add_messages(messages)
        assert len(result) == 2
        assert result[0].content == "hi"
        assert result[1].content == "hello"
        assert db.add.call_count == 2


class TestConversationServiceGetHistory:
    @pytest.mark.asyncio
    async def test_get_history(self) -> None:
        db = AsyncMock()
        m1 = _mock_message("m1", "s1", "user", "hi")
        m2 = _mock_message("m2", "s1", "assistant", "hello")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[m1, m2])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.get_history("s1", limit=20)
        assert len(result) == 2
        assert result[0].content == "hi"

    @pytest.mark.asyncio
    async def test_get_history_empty(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.get_history("s1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_history_with_before_id(self) -> None:
        db = AsyncMock()
        before_msg = _mock_message("m2", "s1")
        db.get = AsyncMock(return_value=before_msg)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.get_history("s1", before_id="m2")
        assert result == []


class TestConversationServiceGetLastNMessages:
    @pytest.mark.asyncio
    async def test_get_last_n_returns_reversed(self) -> None:
        db = AsyncMock()
        m1 = _mock_message("m1", "s1", "user", "first")
        m2 = _mock_message("m2", "s1", "assistant", "second")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[m2, m1])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.get_last_n_messages("s1", n=2)
        assert len(result) == 2
        assert result[0].content == "first"
        assert result[1].content == "second"


class TestConversationServiceGetSessionMessageCount:
    @pytest.mark.asyncio
    async def test_message_count(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=42)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.get_session_message_count("s1")
        assert result == 42

    @pytest.mark.asyncio
    async def test_message_count_zero(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=0)
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.get_session_message_count("s1")
        assert result == 0


class TestConversationServiceMessagesToDicts:
    def test_user_message(self) -> None:
        db = MagicMock()
        svc = ConversationService(db)
        msg = _mock_message(role="user", content="hello")
        result = svc.messages_to_dicts([msg])
        assert result == [{"role": "user", "content": "hello"}]

    def test_assistant_message(self) -> None:
        db = MagicMock()
        svc = ConversationService(db)
        msg = _mock_message(role="assistant", content="hi there")
        result = svc.messages_to_dicts([msg])
        assert result == [{"role": "assistant", "content": "hi there"}]

    def test_assistant_message_with_tool_calls(self) -> None:
        db = MagicMock()
        svc = ConversationService(db)
        msg = _mock_message(role="assistant", content="using tool")
        msg.tool_calls = [{"id": "call_1", "function": {"name": "search", "arguments": "{}"}}]
        result = svc.messages_to_dicts([msg])
        assert result[0]["tool_calls"] == msg.tool_calls

    def test_tool_message_uses_tool_result(self) -> None:
        db = MagicMock()
        svc = ConversationService(db)
        msg = _mock_message(role="tool", content="original content")
        msg.tool_result = '{"found": 3}'
        result = svc.messages_to_dicts([msg])
        assert result[0]["content"] == '{"found": 3}'


class TestConversationServiceLoadHistoryForContext:
    @pytest.mark.asyncio
    async def test_load_history_for_context(self) -> None:
        db = AsyncMock()
        m1 = _mock_message("m1", "s1", "user", "hi")
        m2 = _mock_message("m2", "s1", "assistant", "hello")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all = MagicMock(return_value=[m2, m1])
        db.execute = AsyncMock(return_value=mock_result)

        svc = ConversationService(db)
        result = await svc.load_history_for_context("s1", max_turns=10)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
