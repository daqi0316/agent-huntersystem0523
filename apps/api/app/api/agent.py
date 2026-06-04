"""统一 Agent API — 对话式招聘助手入口。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user, get_current_user_id, get_db
from app.core.database import AsyncSession
from app.commands import CommandContext, role_to_permissions
from app.schemas.jd_generator import JDGenerateRequest, JDGenerateResponse
from app.schemas.knowledge import KnowledgeQueryRequest, KnowledgeQueryResponse
from app.services.agent_service import chat_with_tools
from app.services.jd_generator import JDGeneratorService
from app.services.knowledge import KnowledgeService

router = APIRouter()


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")
    history: list[dict] = Field(default_factory=list, description="历史消息记录（可选）")
    system_prompt: str | None = Field(None, max_length=2000, description="自定义 System Prompt（可选）")
    session_id: str | None = Field(None, max_length=255, description="跨会话记忆 ID（前端生成，首次留空则服务端生成）")
    attachment: dict | None = Field(None, description="附件信息（file_url, file_type, filename）")


class AgentToolCallInfo(BaseModel):
    name: str = ""
    args: dict = {}
    error: str | None = None
    needs_human: bool = False


class AgentActionInfo(BaseModel):
    agent: str = ""
    status: str = ""
    summary: str = ""


class AgentChatResponse(BaseModel):
    success: bool = True
    reply: str = ""
    model: str = ""
    tool_calls: list[AgentToolCallInfo] = []
    agent_actions: list[AgentActionInfo] = Field(default_factory=list, description="Orchestrator 编排的子任务执行记录")


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    req: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    messages = list(req.history) + [{"role": "user", "content": req.message}]
    command_ctx = CommandContext(
        session_id=req.session_id or "",
        user_id=current_user["user_id"],
        permissions=role_to_permissions(current_user.get("role")),
        user_role=current_user.get("role"),
        db=db,
    )
    result = await chat_with_tools(
        messages,
        user_id=current_user["user_id"],
        session_id=req.session_id,
        system_prompt=req.system_prompt,
        attachment=req.attachment,
        command_context=command_ctx,
    )

    from app.api.agent_events import emit_chat_response
    tool_calls_payload = [
        tc if isinstance(tc, dict) else tc.dict()
        for tc in (result.get("tool_calls") or [])
    ]
    await emit_chat_response(
        user_id=current_user["user_id"],
        reply=result["reply"],
        tool_calls=tool_calls_payload,
        model=result.get("model", ""),
    )

    return AgentChatResponse(
        reply=result["reply"],
        model=result.get("model", ""),
        tool_calls=[
            AgentToolCallInfo(**tc) for tc in tool_calls_payload
        ],
        agent_actions=[
            AgentActionInfo(**ac) for ac in result.get("agent_actions", [])
        ],
    )


@router.post("/generate-jd", response_model=JDGenerateResponse)
async def generate_jd(
    req: JDGenerateRequest,
    _user_id: str = Depends(get_current_user_id),
):
    """生成职位描述（JD），支持 Gen-Eval 迭代优化。"""
    service = JDGeneratorService()
    result = await service.generate_jd(
        title=req.title,
        requirements=req.requirements,
        preferences=req.preferences or "",
        auto_improve=req.auto_improve,
    )
    return JDGenerateResponse(
        success=True,
        data=result["final_output"],
        iterations=result["iterations"],
        total_iterations=result["total_iterations"],
        passed=result["passed"],
    )


@router.post("/knowledge-query", response_model=KnowledgeQueryResponse)
async def knowledge_query(
    req: KnowledgeQueryRequest,
    _user_id: str = Depends(get_current_user_id),
):
    """知识库 RAG 问答。"""
    service = KnowledgeService()
    result = await service.query(query=req.query, top_k=req.top_k)
    return KnowledgeQueryResponse(
        success=True,
        answer=result["answer"],
        sources=result["sources"],
    )
