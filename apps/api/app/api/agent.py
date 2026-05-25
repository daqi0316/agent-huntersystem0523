"""统一 Agent API — 对话式招聘助手入口。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user_id
from app.services.agent_service import chat_with_tools

router = APIRouter()


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")
    history: list[dict] = Field(default_factory=list, description="历史消息记录（可选）")


class AgentToolCallInfo(BaseModel):
    name: str = ""
    args: dict = {}
    error: str | None = None


class AgentChatResponse(BaseModel):
    success: bool = True
    reply: str = ""
    tool_calls: list[AgentToolCallInfo] = []


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    req: AgentChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """统一 Agent 对话入口。支持自然语言完成所有招聘操作。"""
    messages = list(req.history) + [{"role": "user", "content": req.message}]
    result = await chat_with_tools(messages, user_id=user_id)

    return AgentChatResponse(
        reply=result["reply"],
        tool_calls=[
            AgentToolCallInfo(**tc) for tc in result["tool_calls"]
        ],
    )
