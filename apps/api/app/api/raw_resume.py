"""v0.6a: raw_resume async API — submit + poll + WS 进度推送。

POST /raw-resumes/parse:           submit (enqueue RQ task, 返 raw_resume_id + task_id)
GET  /raw-resumes/{id}/status:      poll (读 raw_resumes 表 status)
WS   /raw-resumes/{id}/progress:    实时进度推送 (?token= 鉴权, CLAUDE.md 模式 5)
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.dependencies import get_current_user_id
from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.models.raw_resume import RawResume, RawResumeStatus, new_raw_resume_id
from app.services.parse_task import enqueue_parse_task, poll_parse_task

logger = logging.getLogger(__name__)

router = APIRouter()


class ParseSubmitRequest(BaseModel):
    content: str = ""
    file_url: str = ""
    file_type: str = ""
    filename: str = ""
    target_job_id: str = ""
    auto_create: bool = True


class ParseSubmitResponse(BaseModel):
    raw_resume_id: str
    task_id: str
    status: str = "processing"


@router.post("/parse", response_model=ParseSubmitResponse)
async def submit_parse(
    req: ParseSubmitRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Submit a parse task. Returns raw_resume_id + RQ task_id immediately.

    流程:
      1. 落 raw_resumes (status=processing, raw_text 完整保存)
      2. enqueue RQ task (worker 调 _do_extract_and_link 跑 LLM + 状态机更新)
      3. 立刻返 task_id (不等 LLM)
    """
    if not req.content and not req.file_url:
        raise HTTPException(status_code=400, detail="content or file_url required")

    content = req.content

    raw_resume_id = new_raw_resume_id()
    async with AsyncSessionLocal() as db:
        rr = RawResume(
            id=raw_resume_id,
            raw_text=content,
            file_url=req.file_url or None,
            file_type=req.file_type or None,
            filename=req.filename or None,
            target_job_id=req.target_job_id or None,
            status=RawResumeStatus.PROCESSING,
        )
        db.add(rr)
        await db.commit()

    try:
        task_id = enqueue_parse_task(
            raw_resume_id=raw_resume_id,
            content=content,
            auto_create=req.auto_create,
        )
    except Exception as e:
        logger.error("Failed to enqueue parse task for %s: %s", raw_resume_id, e)
        async with AsyncSessionLocal() as db:
            stuck = await db.get(RawResume, raw_resume_id)
            if stuck is not None:
                stuck.status = RawResumeStatus.FAILED
                stuck.error_message = f"enqueue_failed: {e}"
                await db.commit()
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {e}")

    return ParseSubmitResponse(
        raw_resume_id=raw_resume_id,
        task_id=task_id,
        status="processing",
    )


@router.get("/{raw_resume_id}/status")
async def get_status(
    raw_resume_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Poll task status by raw_resume_id.

    优先读 raw_resumes.status（_do_extract_and_link 写回, source of truth）。
    """
    result = await poll_parse_task(raw_resume_id)
    if result is None:
        raise HTTPException(status_code=404, detail="raw_resume not found")
    return result


async def _authenticate_ws(websocket: WebSocket) -> str | None:
    """WS 鉴权: header 优先 → ?token= 兜底 (CLAUDE.md 模式 5 推 WS 版)。"""
    auth = websocket.headers.get("authorization", "")
    token: str | None = None
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return None
    try:
        payload = decode_access_token(token)
    except Exception:
        await websocket.close(code=1008)
        return None
    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=1008)
        return None
    return user_id


@router.websocket("/{raw_resume_id}/progress")
async def ws_progress(websocket: WebSocket, raw_resume_id: str):
    """WS 端点 — 轮询 raw_resumes.status, 状态变化时推送, terminal 关闭。

    鉴权: header 优先 → ?token= 兜底 (与 SSE 一致, CLAUDE.md 模式 5)。
    推送间隔: 200ms (LLM parse 通常 1-3s, 200ms 平衡实时性 + DB 压力)。
    terminal 状态 (parsed/failed) 推 1 次后关闭连接。

    断线重连: 客户端自己重新 connect, 不重发历史消息（前端可先 poll 一次当前状态）。
    """
    user_id = await _authenticate_ws(websocket)
    if user_id is None:
        return

    await websocket.accept()
    await _poll_state_until_terminal(websocket, raw_resume_id, websocket.send_json)


async def _poll_state_until_terminal(
    websocket: WebSocket,
    raw_resume_id: str,
    send_json,
) -> None:
    """v0.6b: 状态变化轮询循环 — 抽成独立函数便于 unit test。

    状态变化时调 send_json 推送, terminal 状态 (parsed/failed/not_found) 后停止。
    """
    last_status: str | None = None
    try:
        while True:
            result = await poll_parse_task(raw_resume_id)
            if result is None:
                await send_json({
                    "raw_resume_id": raw_resume_id,
                    "status": "not_found",
                })
                break
            current_status = result["status"]
            if current_status != last_status:
                await send_json(result)
                last_status = current_status
                if current_status in (RawResumeStatus.PARSED.value, RawResumeStatus.FAILED.value):
                    break
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass

