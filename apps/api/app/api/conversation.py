"""Conversation API — 多轮对话 Session & 消息管理 + 初筛对话。

端到端流程:
   1. POST /session → 创建新对话（返回 session_id）
   2. GET  /sessions → 列出用户的所有会话
   3. GET  /session/{id} → 获取单个会话详情
   4. GET  /session/{id}/messages → 获取历史消息
   5. DELETE /session/{id} → 删除会话
   6. PATCH /session/{id} → 更新标题/元数据
   7. POST /session/{id}/screen — 对候选人进行多轮对话式初筛
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.llm import get_llm_client
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Schemas ──


class CreateSessionRequest(BaseModel):
    title: str = Field(default="新对话", max_length=255, description="会话标题")


class SessionResponse(BaseModel):
    id: str
    title: str
    metadata: dict = {}
    message_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class SessionListResponse(BaseModel):
    success: bool = True
    total: int = 0
    sessions: list[SessionResponse] = []


class UpdateSessionRequest(BaseModel):
    title: str | None = Field(None, max_length=255)
    metadata: dict | None = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    tool_calls: list[dict] | None = None
    created_at: str = ""


class MessageListResponse(BaseModel):
    success: bool = True
    total: int = 0
    messages: list[MessageResponse] = []


class DeleteResponse(BaseModel):
    success: bool = True
    message: str = "已删除"


# ── Endpoints ──


@router.post("/session", response_model=SessionResponse)
async def create_session(
    req: CreateSessionRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """创建新对话 Session。"""
    svc = ConversationService(db)
    session = await svc.create_session(user_id, title=req.title)
    return SessionResponse(
        id=session.id,
        title=session.title,
        metadata=session.session_metadata or {},
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else "",
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    limit: int = 20,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """列出用户的对话 Session。"""
    svc = ConversationService(db)
    sessions = await svc.list_sessions(user_id, limit=limit, offset=offset)
    items: list[SessionResponse] = []
    for s in sessions:
        count = await svc.get_session_message_count(s.id)
        items.append(SessionResponse(
            id=s.id, title=s.title, metadata=s.session_metadata or {},
            message_count=count,
            created_at=s.created_at.isoformat() if s.created_at else "",
            updated_at=s.updated_at.isoformat() if s.updated_at else "",
        ))
    return SessionListResponse(total=len(items), sessions=items)


@router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取单个 Session 详情。"""
    svc = ConversationService(db)
    session = await svc.get_session(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    count = await svc.get_session_message_count(session.id)
    return SessionResponse(
        id=session.id, title=session.title, metadata=session.session_metadata or {},
        message_count=count,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else "",
    )


@router.delete("/session/{session_id}", response_model=DeleteResponse)
async def delete_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除对话 Session（连带消息一起删除）。"""
    svc = ConversationService(db)
    session = await svc.get_session(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    await svc.delete_session(session_id)
    return DeleteResponse()


@router.patch("/session/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    req: UpdateSessionRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """更新 Session 标题或元数据。"""
    svc = ConversationService(db)
    session = await svc.get_session(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")

    if req.title is not None:
        session = await svc.update_session_title(session_id, req.title)
    if req.metadata is not None:
        session = await svc.update_session_metadata(session_id, req.metadata)

    count = await svc.get_session_message_count(session.id)
    return SessionResponse(
        id=session.id, title=session.title, metadata=session.session_metadata or {},
        message_count=count,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else "",
    )


@router.get("/session/{session_id}/messages", response_model=MessageListResponse)
async def get_messages(
    session_id: str,
    limit: int = 50,
    before_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取 Session 的历史消息。"""
    svc = ConversationService(db)
    session = await svc.get_session(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = await svc.get_history(session_id, limit=limit, before_id=before_id)
    return MessageListResponse(
        total=len(msgs),
        messages=[
            MessageResponse(
                id=m.id, role=m.role, content=m.content,
                tool_calls=m.tool_calls,
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
            for m in msgs
        ],
    )


class ScreenChatRequest(BaseModel):
    session_id: str = Field(..., description="对话 Session ID")
    message: str = Field(..., min_length=1, max_length=5000, description="用户消息")
    candidate_id: str = Field(..., description="要讨论的候选人 ID")
    job_id: str = Field(..., description="关联的职位 ID")


class ScreenChatResponse(BaseModel):
    success: bool = True
    reply: str = ""
    session_id: str = ""


SCREEN_CHAT_SYSTEM_PROMPT = (
    "你是一个AI招聘初筛助手，负责通过多轮对话对候选人进行深入评估。\n\n"
    "## 你的职责\n"
    "1. 理解用户对候选人的提问（如\"他的技术怎么样？\"\"有什么风险？\"\"适合这个岗位吗？\"）\n"
    "2. 基于候选人简历信息和职位要求提供专业判断\n"
    "3. 如果用户没有明确问题，主动引导用户关注关键评估维度\n"
    "4. 回答要专业、简洁、有依据，引用候选人的具体信息\n\n"
    "## 评估维度\n"
    "- technical: 技术能力匹配度\n"
    "- experience: 经验匹配度\n"
    "- education: 学历背景\n"
    "- skills: 技能覆盖度\n"
    "- culture: 文化适配\n"
    "- potential: 成长潜力\n\n"
    "## 对话风格\n"
    "- 用中文回答\n"
    "- 先给出结论，再提供依据\n"
    "- 不确定时诚实地说不确定，不要编造\n"
    "- 可以提出追问建议帮助用户做决定\n"
    "你不必在一轮中完成所有评估，通过多轮对话深入了解。"
)


@router.post("/session/{session_id}/screen", response_model=ScreenChatResponse)
async def screen_chat(
    session_id: str,
    req: ScreenChatRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Multi-turn screening chat against a candidate + job context.
    Preserves conversation history for follow-up questions.
    """
    svc = ConversationService(db)
    session = await svc.get_session(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")

    from app.models.candidate import Candidate
    from app.models.job_position import JobPosition
    from sqlalchemy import select

    cand_result = await db.execute(select(Candidate).where(Candidate.id == req.candidate_id))
    candidate = cand_result.scalar_one_or_none()
    job_result = await db.execute(select(JobPosition).where(JobPosition.id == req.job_id))
    job = job_result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")
    if not job:
        raise HTTPException(status_code=404, detail="职位不存在")

    context_lines = [
        f"候选人: {candidate.name or '未知'}",
        f"技能: {', '.join(candidate.skills or [])}",
        f"经验: {candidate.experience_years or '未知'}年",
    ]
    if candidate.current_company:
        context_lines.append(f"当前公司: {candidate.current_company}")
    if candidate.current_title:
        context_lines.append(f"当前职位: {candidate.current_title}")
    if candidate.education:
        context_lines.append(f"学历: {candidate.education}")
    context_lines.append(f"\n职位: {job.title}")
    if job.requirements:
        context_lines.append(f"要求: {job.requirements}")

    candidate_context = "\n".join(context_lines)

    history = await svc.get_last_n_messages(session_id, n=20)
    llm = get_llm_client()
    messages = [
        {"role": "system", "content": SCREEN_CHAT_SYSTEM_PROMPT},
        {"role": "system", "content": f"## 当前评估上下文\n\n{candidate_context}"},
    ]

    for m in history:
        if m.role == "system":
            continue
        messages.append({"role": m.role, "content": m.content})

    messages.append({"role": "user", "content": req.message})

    try:
        reply = await llm.chat(messages, temperature=0.3, max_tokens=2048)
    except Exception as e:
        logger.error("Screen chat LLM call failed: %s", e)
        reply = "抱歉，我暂时无法完成评估，请稍后重试。"

    await svc.add_message(session_id, user_id, "user", req.message)
    await svc.add_message(session_id, user_id, "assistant", reply)

    return ScreenChatResponse(reply=reply, session_id=session_id)
