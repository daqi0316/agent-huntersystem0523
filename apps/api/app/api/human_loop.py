"""图7: Human-in-Loop API — 面试安排 + 人类确认。"""

from fastapi import APIRouter, HTTPException

from app.schemas.screening import HumanLoopRequest, HumanLoopResponse
from app.agents.human_loop import HumanLoopAgent

router = APIRouter()
agent = HumanLoopAgent(name="interview_scheduler")


@router.post("/schedule", response_model=HumanLoopResponse)
async def schedule_interview(req: HumanLoopRequest):
    """图7: 面试安排（AI 生成建议 → 等待人类确认）。"""
    result = await agent.run({
        "action_type": req.action_type,
        "params": req.params,
    })
    return HumanLoopResponse(
        success=True,
        status=result.get("status", "awaiting_approval"),
        approval=result.get("approval", {}),
    )


@router.post("/approve", response_model=HumanLoopResponse)
async def approve_action(req: HumanLoopRequest):
    """图7: 人类确认或拒绝提案。"""
    if not req.approval_id:
        raise HTTPException(status_code=400, detail="approval_id is required")
    result = await agent.confirm(
        approval_id=req.approval_id,
        approved=req.approved,
        feedback=req.feedback,
    )
    return HumanLoopResponse(
        success="error" not in result,
        status=result.get("status", "unknown"),
        approval=result,
    )


@router.get("/pending")
async def list_pending():
    """列出所有待审批提案。"""
    return {
        "success": True,
        "items": agent.get_pending_proposals(),
    }


@router.get("/history")
async def list_history(limit: int = 50):
    """列出已处理的审批历史。"""
    return {
        "success": True,
        "items": agent.get_approval_history(limit=limit),
    }


@router.post("/stop")
async def stop_emergency():
    """图7: 紧急停止 — 清除所有待审批项。"""
    count = agent.get_pending_count()
    agent._pending_purge_all()
    return {
        "success": True,
        "message": "Emergency stop triggered",
        "cleared_count": count,
    }
