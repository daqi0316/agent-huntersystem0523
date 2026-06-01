"""图7: Human-in-Loop API — 面试安排 + 人类确认 + SSE 推送。"""

import asyncio
import hashlib
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agents.human_loop import HumanLoopAgent
from app.core.dependencies import get_current_user_id
from app.core.response import success, error
from app.core.sse import sse_event, sse_error, sse_headers
from app.schemas.screening import HumanLoopRequest, HumanLoopResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level agent instance (singleton shared across endpoints)
agent = HumanLoopAgent(name="interview_scheduler")

# SSE streaming constants
_POLL_INTERVAL = 2.0
_STREAM_TIMEOUT = 300


def _hash_pending(items: list[dict]) -> str:
    """Compute a quick content hash of the pending items list.

    Used to detect changes between polls so we only emit when data changes.
    """
    raw = json.dumps(items, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


async def _pending_proposals_generator():
    """SSE 事件生成器：持续推送待审批提案列表，仅在有变化时推送。"""
    prev_hash = ""
    elapsed = 0.0

    while elapsed < _STREAM_TIMEOUT:
        try:
            items = await agent.get_pending_proposals()
            current_hash = _hash_pending(items)

            if current_hash != prev_hash:
                yield sse_event("pending_updated", {
                    "data": items,
                    "timestamp": asyncio.get_event_loop().time(),
                })
                prev_hash = current_hash
        except Exception as exc:
            logger.warning("SSE poll error: %s", exc)
            yield sse_error(str(exc))

        await asyncio.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL

    yield sse_event("timeout", {"message": "SSE connection timed out"})


@router.get("/events")
async def human_loop_events():
    """SSE 待审批提案流 — 实时推送 pending 列表变化。"""
    return StreamingResponse(
        _pending_proposals_generator(),
        media_type="text/event-stream",
        headers=sse_headers(),
    )


@router.post("/schedule", response_model=HumanLoopResponse)
async def schedule_interview(
    req: HumanLoopRequest,
    user_id: str = Depends(get_current_user_id),
):
    """图7: 面试安排（AI 生成建议 → 等待人类确认）。"""
    result = await agent.run({
        "action_type": req.action_type,
        "params": req.params,
        "user_id": user_id,
    })
    return HumanLoopResponse(
        success=True,
        status=result.get("status", "awaiting_approval"),
        approval=result.get("approval", {}),
    )


@router.post("/approve", response_model=HumanLoopResponse)
async def approve_action(
    req: HumanLoopRequest,
    user_id: str = Depends(get_current_user_id),
):
    """图7: 人类确认或拒绝提案。"""
    if not req.approval_id:
        return error("approval_id is required", status_code=400)
    result = await agent.confirm(
        approval_id=req.approval_id,
        user_id=user_id,
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
    data = await agent.get_pending_proposals()
    return success(data)


@router.get("/history")
async def list_history(limit: int = 50):
    """列出已处理的审批历史。"""
    data = await agent.get_approval_history(limit=limit)
    return success(data)


@router.post("/resume")
async def resume_after_approval(req: HumanLoopRequest):
    """审批通过后恢复 Orchestrator 编排执行。

    PR-V.2: 优先用 LangGraph checkpointer 恢复（PR-V.1 写入的 paused 状态），
    失败/无索引时降级到 legacy OrchestratorSession（PR-V.4 删除）。

    Graph 流程:
    1. 从 Redis 索引 `appr:graph_thread:{approval_id}` 反查 thread_id
    2. graph.get_state(config) 读出暂停时的 OrchestratorState
    3. 找到匹配 approval_id 的 awaiting_approval entry，标记为 approved
    4. 清空 paused_at_level，status → running
    5. graph.update_state(config, {...}) 提交变更
    6. graph.ainvoke(None, config) 从断点继续执行后续 level
    7. 从结果汇总 outputs/status/summary
    """
    if not req.approval_id:
        return error("approval_id is required", status_code=400)

    status = await agent.get_approval_status(req.approval_id)
    if status is None:
        return error("approval_id not found", status_code=404)

    if status["status"] != "approved":
        return error(f"approval status is '{status['status']}', expected 'approved'", status_code=400)

    thread_id = await _resolve_graph_thread_id(req.approval_id)
    if thread_id:
        return await _resume_via_graph(req.approval_id, thread_id)

    return await _resume_legacy(req.approval_id)


async def _resolve_graph_thread_id(approval_id: str) -> str | None:
    """从 Redis 索引反查 graph thread_id。无索引 → 走 legacy 路径。"""
    from app.core.redis import get_redis

    try:
        client = await get_redis()
    except Exception:
        return None
    if client is None:
        return None
    try:
        raw = await client.get(f"appr:graph_thread:{approval_id}")
    except Exception as e:
        logger.warning("Failed to read approval index %s: %s", approval_id, e)
        return None
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else raw


async def _resume_via_graph(approval_id: str, thread_id: str) -> dict:
    """通过 LangGraph checkpointer 恢复 multi-stage 执行。"""
    from app.api.orchestrator import _get_graph
    from app.core.redis import get_redis

    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    snap = graph.get_state(config)
    if snap is None or not snap.values:
        return error("graph state not found for thread", status_code=404)

    state = snap.values
    paused_at_level = state.get("paused_at_level")
    if paused_at_level is None:
        return error("graph state is not paused (no awaiting_approval)", status_code=400)

    results = list(state.get("results") or [])
    matched_idx = None
    for i, r in enumerate(results):
        if not isinstance(r, dict):
            continue
        if r.get("status") != "awaiting_approval":
            continue
        aid = (r.get("details") or {}).get("approval", {}).get("approval_id", "")
        if aid == approval_id:
            matched_idx = i
            break

    if matched_idx is None:
        return error(
            f"approval_id {approval_id} not found in graph state awaiting list",
            status_code=404,
        )

    results[matched_idx] = {
        **results[matched_idx],
        "status": "approved",
        "summary": (results[matched_idx].get("summary", "") + "（已审批）").strip(),
    }
    update_patch = {
        "results": results,
        "paused_at_level": None,
        "status": "running",
    }
    graph.update_state(config, update_patch)

    try:
        final = await graph.ainvoke(None, config=config)
    except Exception as e:
        logger.error("Graph resume failed for thread %s: %s", thread_id, e)
        return error(f"graph resume failed: {e}", status_code=500)

    final_results = final.get("results") or results
    succeeded = sum(1 for r in final_results if r and r.get("status") in ("completed", "approved"))
    failed = sum(1 for r in final_results if r and r.get("status") == "failed")
    next_awaiting = sum(1 for r in final_results if r and r.get("status") == "awaiting_approval")
    final_status = final.get("status", "completed")

    if next_awaiting > 0:
        summary = f"编排继续等待审批: {next_awaiting} 个子任务待确认"
    elif failed == 0 and final_status != "failed":
        summary = "编排全部完成"
        final_status = "completed"
    else:
        summary = f"编排部分完成: {succeeded}/{len(final_results)}"
        final_status = "partial"

    try:
        client = await get_redis()
        if client is not None:
            await client.delete(f"appr:graph_thread:{approval_id}")
    except Exception as e:
        logger.warning("Failed to clean approval index %s: %s", approval_id, e)

    return success({
        "agent": "orchestrator",
        "status": final_status,
        "summary": summary,
        "outputs": final_results,
        "total_sub_tasks": len(final_results),
        "succeeded": succeeded,
        "failed": failed,
        "awaiting_approval": next_awaiting,
    })


async def _resume_legacy(approval_id: str) -> dict:
    """PR-V.4 之前的兼容路径：从 OrchestratorSession 恢复（无 graph 索引时）。"""
    from app.agents.orchestrator_session import OrchestratorSession
    from app.agents.orchestrator_agent import OrchestratorAgent

    session = await OrchestratorSession.find_by_approval_id(approval_id)
    if session is None:
        return error("orchestrator session not found", status_code=404)

    orch = OrchestratorAgent()
    orch.shared_context = dict(session.shared_context)

    for i, r in enumerate(session.results):
        if r and r.get("status") == "awaiting_approval":
            aid = (r.get("details") or {}).get("approval", {}).get("approval_id", "")
            if aid == approval_id:
                session.results[i] = {**r, "status": "approved", "summary": r.get("summary", "") + "（已审批）"}

    remaining_levels = session.levels[session.paused_at_level:]
    final_outputs = list(session.results)

    for level in remaining_levels:
        coros = [orch.execute_sub_task(session.sub_tasks[i]) for i in level]
        level_results = await asyncio.gather(*coros, return_exceptions=True)
        for i, raw in zip(level, level_results):
            if isinstance(raw, Exception):
                final_outputs[i] = {
                    "agent": session.sub_tasks[i].get("type", "unknown"),
                    "status": "failed",
                    "summary": f"执行异常: {str(raw)[:100]}",
                    "result": {},
                    "details": {"error": str(raw)},
                }
            else:
                final_outputs[i] = raw

    succeeded = sum(1 for r in final_outputs if r and r.get("status") in ("completed", "approved"))
    failed = sum(1 for r in final_outputs if r and r.get("status") == "failed")
    next_awaiting = sum(1 for r in final_outputs if r and r.get("status") == "awaiting_approval")

    if next_awaiting > 0:
        status_text = "awaiting_approval"
        summary = f"编排继续等待审批: {next_awaiting} 个子任务待确认"
    elif failed == 0:
        status_text = "completed"
        summary = "编排全部完成"
    else:
        status_text = "partial"
        summary = f"编排部分完成: {succeeded}/{len(final_outputs)}"

    result = {
        "agent": "orchestrator",
        "status": status_text,
        "summary": summary,
        "outputs": final_outputs,
        "total_sub_tasks": len(final_outputs),
        "succeeded": succeeded,
        "failed": failed,
        "awaiting_approval": next_awaiting,
    }

    await session.delete()

    return success(result)


@router.post("/stop")
async def stop_emergency():
    """图7: 紧急停止 — 清除所有待审批项。"""
    count = await agent.get_pending_count()
    await agent._pending_purge_all()
    return success({"message": "Emergency stop triggered", "cleared_count": count})
