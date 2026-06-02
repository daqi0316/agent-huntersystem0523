"""ConversationService — 多轮对话持久化 + Session 管理。

职责：
  1. 管理 conversation_sessions（创建/列表/删除）
  2. 持久化 conversation_messages（追加/查询）
  3. 自动注入历史消息到 agent 上下文
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class ConversationService:
    """对话持久化服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Session CRUD ──

    async def create_session(self, user_id: str, title: str = "新对话") -> ConversationSession:
        """创建新对话 Session。"""
        session = ConversationSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            metadata={},
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info("Created conversation session %s for user %s", session.id, user_id)
        return session

    async def list_sessions(
        self, user_id: str, limit: int = 20, offset: int = 0,
    ) -> list[ConversationSession]:
        """列出用户的所有对话 Session，按更新时间倒序。"""
        stmt = (
            select(ConversationSession)
            .where(ConversationSession.user_id == user_id)
            .order_by(desc(ConversationSession.updated_at))
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_session(self, session_id: str) -> ConversationSession | None:
        """获取单个 Session。"""
        stmt = select(ConversationSession).where(ConversationSession.id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_session(self, session_id: str) -> bool:
        """删除 Session 及其所有消息。CASCADE 会处理消息表。"""
        stmt = delete(ConversationSession).where(ConversationSession.id == session_id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def update_session_metadata(
        self, session_id: str, metadata: dict,
    ) -> ConversationSession | None:
        """更新 Session 元数据（合并写入）。"""
        session = await self.get_session(session_id)
        if not session:
            return None
        current = dict(session.session_metadata or {})
        current.update(metadata)
        session.session_metadata = current
        session.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def update_session_title(self, session_id: str, title: str) -> ConversationSession | None:
        """更新 Session 标题。"""
        session = await self.get_session(session_id)
        if not session:
            return None
        session.title = title
        session.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    # ── Message CRUD ──

    async def add_message(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        tool_calls: list[dict] | None = None,
        tool_result: dict | None = None,
    ) -> ConversationMessage:
        """追加一条对话消息，自动创建 session 如果不存在。"""
        session = await self.get_session(session_id)
        if not session:
            session = ConversationSession(
                id=session_id,
                user_id=user_id,
                title=f'会话 {session_id[:8]}',
            )
            self.db.add(session)
        msg = ConversationMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_result=tool_result,
        )
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def add_messages(self, messages: list[dict]) -> list[ConversationMessage]:
        """批量追加消息（不 commit — 由调用方控制事务）。"""
        created: list[ConversationMessage] = []
        for m in messages:
            msg = ConversationMessage(
                id=str(uuid.uuid4()),
                session_id=m["session_id"],
                user_id=m["user_id"],
                role=m["role"],
                content=m.get("content", ""),
                tool_calls=m.get("tool_calls"),
                tool_result=m.get("tool_result"),
            )
            self.db.add(msg)
            created.append(msg)
        await self.db.commit()
        return created

    async def get_history(
        self,
        session_id: str,
        limit: int = 20,
        before_id: str | None = None,
    ) -> list[ConversationMessage]:
        """获取 Session 历史消息，按创建时间升序。"""
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.created_at.asc())
            .limit(limit)
        )
        if before_id:
            before_msg = await self.db.get(ConversationMessage, before_id)
            if before_msg:
                stmt = stmt.where(ConversationMessage.created_at < before_msg.created_at)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_last_n_messages(
        self, session_id: str, n: int = 20,
    ) -> list[ConversationMessage]:
        """获取最近 N 条消息（按时间倒序取 N 条，返回正序）。"""
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(desc(ConversationMessage.created_at))
            .limit(n)
        )
        result = await self.db.execute(stmt)
        msgs = list(result.scalars().all())
        msgs.reverse()
        return msgs

    async def get_session_message_count(self, session_id: str) -> int:
        """统计 Session 的消息数量。"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(ConversationMessage).where(
            ConversationMessage.session_id == session_id
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ── 上下文辅助 ──

    def messages_to_dicts(self, msgs: list[ConversationMessage]) -> list[dict]:
        """将 ORM 消息转换为 LLM 消息格式。"""
        result: list[dict] = []
        for m in msgs:
            entry: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls and m.role == "assistant":
                entry["tool_calls"] = m.tool_calls
            if m.tool_result and m.role == "tool":
                entry["content"] = m.tool_result  # tool messages carry result as content
            result.append(entry)
        return result

    async def load_history_for_context(
        self, session_id: str, max_turns: int = 20,
    ) -> list[dict]:
        """加载历史消息供 agent 上下文注入。返回 LLM 消息格式列表。"""
        msgs = await self.get_last_n_messages(session_id, max_turns)
        return self.messages_to_dicts(msgs)
