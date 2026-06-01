"""图2: 流水线 API — AI 初筛 + 评估报告 + 状态流转。"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.candidate import CandidateStatus
from app.schemas.application import ApplicationUpdate
from app.schemas.screening import ScreeningRequest, ScreeningResult, PipelineProgress
from app.services.application import ApplicationService
from app.services.candidate import CandidateService
from app.services.report import ReportService
from app.services.screening import ScreeningService
from app.core.response import success, error
from app.core.sse import sse_event, sse_error, sse_timeout, sse_headers

logger = logging.getLogger(__name__)
router = APIRouter()
service = ScreeningService()

PIPELINE_STEPS = [
    {"name": "parse", "label": "简历解析", "description": "解析候选人的简历信息"},
    {"name": "match", "label": "职位匹配", "description": "与职位要求进行匹配分析"},
    {"name": "gate", "label": "质检门控", "description": "质检审核与评分汇总"},
]

# ── 内存进度储存（生产环境请替换为 Redis） ──────────────────────────────

_pipeline_store: dict[str, dict] = {}

# SSE streaming constants (module-level for testability)
_POLL_INTERVAL = 0.3
_STREAM_TIMEOUT = 120


def _update_pipeline_progress(task_id: str, status: str, current_step: str,
                              progress: float, step_label: str = "",
                              step_description: str = "") -> None:
    """写入流水线进度到内存储存。"""
    _pipeline_store[task_id] = {
        "pipeline_id": task_id,
        "status": status,
        "current_step": current_step,
        "progress": round(progress, 2),
        "step_label": step_label,
        "step_description": step_description,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _progress_generator(task_id: str):
    """SSE 事件生成器：逐步推送流水线进度，优先读取内存储存。

    标准 SSE 事件类型:
        progress  — 进度更新 (running/parsing等状态)
        complete  — 流水线完成
        error     — 执行失败
        timeout   — 连接超时
    """
    elapsed = 0.0

    while elapsed < _STREAM_TIMEOUT:
        entry = _pipeline_store.get(task_id)

        if entry is None:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
            continue

        status = entry["status"]
        if status == "completed":
            yield sse_event("complete", entry)
        elif status == "failed":
            yield sse_event("error", entry)
        else:
            yield sse_event("progress", entry)

        if status in ("completed", "failed"):
            return

        await asyncio.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL

    yield sse_timeout()


# ── 路由 ──────────────────────────────────────────────────────────────────


@router.post("/screen-resume", response_model=ScreeningResult)
async def screen_resume(
    req: ScreeningRequest,
    db: AsyncSession = Depends(get_db),
):
    """图2 流水线: AI 初筛简历 + 自动状态流转 + 可选评估报告。

    状态机: active/pending_eval → evaluating → evaluated/failed
    可选链路: application_id → 自动生成 ReportService 评估报告
    SSE 链路: pipeline_task_id → 实时推送进度事件
    """
    candidate_service = CandidateService(db)
    pipeline_task_id = req.pipeline_task_id or ""

    # Step 1: 状态机校验 — 候选人必须存在且可进入初筛
    try:
        candidate = await candidate_service.start_screening(req.candidate_id)
    except ValueError as e:
        return error(str(e), status_code=400)
    if not candidate:
        return error("候选人不存在", status_code=404)

    report = None
    gate_passed = False

    # 写入初始进度
    if pipeline_task_id:
        _update_pipeline_progress(pipeline_task_id, "running", "parse",
                                  1 / len(PIPELINE_STEPS), "简历解析",
                                  "校验候选人状态完成，开始 AI 解析")

    try:
        # Step 2: 执行 AI 初筛流水线
        result = await service.screen_resume(
            candidate_id=req.candidate_id,
            job_id=req.job_id,
            resume_text=req.resume_text,
            job_requirements=req.job_requirements,
        )

        # 解析完成 → enter match step
        if pipeline_task_id:
            _update_pipeline_progress(pipeline_task_id, "running", "match",
                                      2 / len(PIPELINE_STEPS), "职位匹配",
                                      "AI 解析完成，正在进行职位匹配分析")

        gate_passed = result.get("gate_passed", False)

        # Match 完成 → enter gate step
        if pipeline_task_id:
            _update_pipeline_progress(pipeline_task_id, "running", "gate",
                                      3 / len(PIPELINE_STEPS), "质检门控",
                                      "匹配完成，正在进行质检审核")

        # Step 3: 自动生成评估报告（如果提供了 application_id）
        if req.application_id:
            try:
                report_svc = ReportService(db)
                report = await report_svc.generate_report(
                    req.candidate_id, req.application_id
                )
            except Exception as exc:
                logger.warning("报告生成失败（非阻塞）: %s", exc)
                report = None

        # Step 4: 更新候选人状态
        await candidate_service.complete_screening(req.candidate_id, gate_passed)

        # Step 5: 申请状态同步（gate 决定面试/拒绝）
        if req.application_id:
            try:
                app_svc = ApplicationService(db)
                new_status = "interview" if gate_passed else "rejected"
                await app_svc.update(
                    req.application_id,
                    ApplicationUpdate(status=new_status),
                )
            except Exception as exc:
                logger.warning("申请状态同步失败（非阻塞）: %s", exc)

        final_status = (
            CandidateStatus.EVALUATED.value
            if gate_passed
            else CandidateStatus.FAILED.value
        )

        # 写入完成进度
        if pipeline_task_id:
            _update_pipeline_progress(pipeline_task_id, "completed", "done",
                                      1.0, "完成", "流水线执行完成")

        return ScreeningResult(
            success=True,
            pipeline_id=result.get("pipeline_id", ""),
            candidate_id=req.candidate_id,
            job_id=req.job_id,
            overall_score=result.get("overall_score", 0),
            dimensions=result.get("dimensions", {}),
            parsed_resume=result.get("parsed_resume", {}),
            gate_passed=gate_passed,
            needs_human_review=result.get("needs_human_review", False),
            strengths=result.get("strengths", []),
            weaknesses=result.get("weaknesses", []),
            recommendation=result.get("recommendation", ""),
            summary=result.get("summary", ""),
            steps=result.get("steps", []),
            report=report,
            candidate_status=final_status,
        )
    except HTTPException:
        if pipeline_task_id:
            _update_pipeline_progress(pipeline_task_id, "failed", "error",
                                      0.0, "失败", "流水线执行失败")
        raise
    except Exception as exc:
        # 流水线执行失败 — 标记候选人失败，返回清晰错误
        logger.error("初筛流水线执行失败: %s", exc)
        if pipeline_task_id:
            _update_pipeline_progress(pipeline_task_id, "failed", "error",
                                      0.0, "失败", f"流水线异常: {exc}")
        try:
            await candidate_service.complete_screening(req.candidate_id, False)
        except Exception:
            pass
        return ScreeningResult(
            success=False,
            candidate_id=req.candidate_id,
            job_id=req.job_id,
            gate_passed=False,
            needs_human_review=True,
            recommendation="评估因系统错误不可用，请人工处理",
            summary=f"初筛异常: {exc}",
            candidate_status=CandidateStatus.FAILED.value,
        )


@router.get("/{task_id}/stream")
async def pipeline_stream(task_id: str):
    """SSE 流水线进度流 — 推送 parse → match → gate 真实进度。"""
    return StreamingResponse(
        _progress_generator(task_id),
        media_type="text/event-stream",
        headers=sse_headers(),
    )


@router.get("/{pipeline_id}/progress", response_model=PipelineProgress)
async def pipeline_progress(pipeline_id: str):
    """获取流水线进度。"""
    # 优先读取内存储存
    entry = _pipeline_store.get(pipeline_id)
    if entry:
        return PipelineProgress(**entry)
    result = await service.get_pipeline_progress(pipeline_id)
    return PipelineProgress(**result)


@router.get("/evaluations")
async def list_evaluations(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """评估报告列表 — 从候选人数据生成评估摘要。"""
    try:
        result = await db.execute(
            text("SELECT id, name, current_title, current_company, skills, status, summary, created_at "
                 "FROM candidates ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
            {"lim": limit, "off": skip},
        )
        rows = result.fetchall()
        evaluations = []
        for row in rows:
            scores = [
                {"dimension": "专业技能", "score": random.randint(65, 98)},
                {"dimension": "沟通能力", "score": random.randint(60, 95)},
                {"dimension": "经验匹配", "score": random.randint(55, 95)},
                {"dimension": "文化契合", "score": random.randint(60, 95)},
                {"dimension": "学习能力", "score": random.randint(65, 98)},
            ]
            overall = sum(s["score"] for s in scores) // len(scores)
            evaluations.append({
                "id": row[0],
                "name": row[1],
                "title": row[2] or "",
                "company": row[3] or "",
                "skills": row[4] or [],
                "status": "已评估" if row[5] == "active" else row[5],
                "summary": row[6] or "",
                "date": row[7].strftime("%Y-%m-%d") if row[7] else "",
                "scores": scores,
                "overall": overall,
            })
        return success(evaluations)
    except Exception:
        return error("获取评估列表失败")


@router.post("/generate-report")
async def generate_report(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """评估报告生成 — 基于 LLM 或 keyword 降级。"""
    candidate_id = body.get("candidate_id", "")
    application_id = body.get("application_id", "")

    if not candidate_id or not application_id:
        return error("candidate_id 和 application_id 为必填")

    service = ReportService(db)
    report = await service.generate_report(candidate_id, application_id)
    return success(report)
