"""Resume Parser built-in tools — parse, batch parse, get profile.

Each tool follows OpenAI function-calling schema with an attached handler.
Handlers delegate to existing services (resume_extractor, CandidateService).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.database import AsyncSessionLocal
from app.llm import get_llm_client
from app.agents.pii_filter import mask_pii
from app.models.raw_resume import RawResume, RawResumeStatus, new_raw_resume_id
from app.services.resume_extractor import extract_from_text
from app.services.candidate import CandidateService
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _do_extract_and_link(
    raw_resume_id: str,
    content: str,
    auto_create: bool = True,
    reuse_candidate_id: bool = False,
) -> dict[str, Any]:
    """v0.5a: 公共函数 — LLM extract + 状态机更新集中。

    v0.6c.1: 加 reuse_candidate_id 参数 (force=False 默认走 reuse=True, force=True 走 reuse=False)。
      - reuse_candidate_id=True:
        - raw_resumes.candidate_id 存在 → svc.update() 复用旧候选人
        - raw_resumes.candidate_id 不存在 → fallback svc.create() (新候选人)
      - reuse_candidate_id=False (默认):
        - svc.create() 创建新候选人 (v0.5a 行为)
        - raw_resumes.candidate_id 覆盖成新 ID (v0.5a 行为)

    parse_resume (reuse_candidate_id=False) 和 v0.5b retry_raw_resume 都调这里。
    状态机边界：processing → parsed/failed。
    auto_create=False 早返回（保持原行为：不创建候选人、不更新 raw_resumes 状态）。
    """
    candidate = None
    try:
        candidate = await extract_from_text(content)
    except Exception as e:
        logger.warning("LLM extraction failed: %s", e)
        candidate = None

    if candidate is None or not candidate.email:
        async with AsyncSessionLocal() as db:
            rr = await db.get(RawResume, raw_resume_id)
            if rr is not None:
                rr.status = RawResumeStatus.FAILED
                rr.error_message = "low_confidence_or_extraction_error"
                await db.commit()
        return {
            "status": "failed",
            "error": {"code": "LOW_CONFIDENCE", "message": "解析置信度过低，无法提取有效信息", "retryable": True},
            "data": {"raw_resume_id": raw_resume_id, "raw_text_snippet": content[:500]},
        }

    candidate_id = ""
    reused = False  # v0.6c.1: 跟踪是否走了 update 路径
    if auto_create:
        try:
            from app.schemas.candidate import CandidateCreate, CandidateUpdate
            async with AsyncSessionLocal() as db:
                # v0.6c.1: reuse 路径先查 raw_resumes.candidate_id
                rr_check = await db.get(RawResume, raw_resume_id)
                existing_candidate_id = rr_check.candidate_id if rr_check else None

                svc = CandidateService(db)
                if reuse_candidate_id and existing_candidate_id:
                    update_data = CandidateUpdate(
                        name=candidate.name or "Unknown",
                        email=candidate.email,
                        phone=candidate.phone or None,
                        skills=list(candidate.skills or []),
                        experience_years=candidate.experience_years,
                        education=candidate.education or None,
                        current_company=candidate.current_company or None,
                        current_title=candidate.current_title or None,
                    )
                    updated = await svc.update(existing_candidate_id, update_data)
                    if updated is None:
                        # candidate 已被外部删, fallback create
                        create_data = CandidateCreate(
                            name=candidate.name or "Unknown",
                            email=candidate.email,
                            phone=candidate.phone or None,
                            skills=list(candidate.skills or []),
                            experience_years=candidate.experience_years,
                            education=candidate.education or None,
                            current_company=candidate.current_company or None,
                            current_title=candidate.current_title or None,
                        )
                        created = await svc.create(create_data)
                        candidate_id = created.id
                        logger.info("fallback create candidate %s (old %s deleted)", candidate_id, existing_candidate_id)
                    else:
                        candidate_id = updated.id
                        reused = True
                        logger.info("Reused candidate %s for raw_resume %s", candidate_id, raw_resume_id)
                else:
                    create_data = CandidateCreate(
                        name=candidate.name or "Unknown",
                        email=candidate.email,
                        phone=candidate.phone or None,
                        skills=list(candidate.skills or []),
                        experience_years=candidate.experience_years,
                        education=candidate.education or None,
                        current_company=candidate.current_company or None,
                        current_title=candidate.current_title or None,
                    )
                    created = await svc.create(create_data)
                    candidate_id = created.id
                    logger.info("Auto-created candidate %s from resume parse", candidate_id)
        except Exception as e:
            logger.warning("Auto-create/update candidate failed (non-blocking): %s", e)
    else:
        return {
            "status": "success",
            "data": {
                "raw_resume_id": raw_resume_id,
                "candidate_id": "",
                "auto_create_skipped": True,
            },
        }

    async with AsyncSessionLocal() as db:
        rr = await db.get(RawResume, raw_resume_id)
        if rr is not None:
            rr.status = RawResumeStatus.PARSED
            # v0.6c.1: reuse 路径保持原 candidate_id, 非 reuse 路径覆盖
            if not reused:
                rr.candidate_id = candidate_id or None
            await db.commit()

    skills = list(candidate.skills or [])
    result = {
        "candidate_id": candidate_id,
        "basic_info": {
            "name": mask_pii(candidate.name or ""),
            "phone": mask_pii(candidate.phone or ""),
            "email": mask_pii(candidate.email),
            "current_company": candidate.current_company or "",
            "current_title": candidate.current_title or "",
            "years_of_experience": candidate.experience_years,
        },
        "work_experience": [],
        "education": [{"school": candidate.education or ""}],
        "skills": skills,
        "match_tags": [],
        "quality_score": _compute_quality(candidate),
        "red_flags": _detect_red_flags(candidate),
        "is_duplicate": False,
    }

    result["confidence"] = 0.85 if candidate.name and candidate.email else 0.6
    return {"status": "success", "data": result}


async def _handle_parse_resume(
    content: str = "",
    file_url: str = "",
    file_type: str = "",
    filename: str = "",
    target_job_id: str = "",
    auto_create: bool = True,
) -> dict[str, Any]:
    """Parse a single resume: extract structured data, assess quality, detect duplicates.

    v0.4d 事务边界（保留）：
    1. 文件解析成功 → raw_text 立刻落 raw_resumes 表 (status=processing)
    2. LLM extract → 创建候选人 + 更新 raw_resumes (status=parsed/failed)
    3. 失败时 raw_text 保留供 retry (v0.5b 工具)
    """
    if not content and not file_url:
        return {"status": "failed", "error": {"code": "INVALID_INPUT", "message": "content or file_url required"}}

    if file_url and not content:
        from app.tools._file_parser_helpers import download_and_save, cleanup_temp_file
        from app.services.resume_parser import parse_resume as _parse_resume_file, ResumeParseError

        tmp_path = None
        try:
            ext = file_type or (filename.rsplit(".", 1)[-1].lower() if filename else "pdf")
            resolved_filename = filename or f"resume.{ext}"
            tmp_path = await download_and_save(file_url, resolved_filename)

            with open(tmp_path, "rb") as f:
                file_bytes = f.read()
            content = _parse_resume_file(file_bytes, resolved_filename)
        except ResumeParseError as e:
            return {"status": "failed", "error": {"code": "PARSE_ERROR", "message": str(e), "retryable": True}}
        except Exception as e:
            return {"status": "failed", "error": {"code": "DOWNLOAD_ERROR", "message": f"文件下载失败: {e}"}}
        finally:
            if tmp_path:
                cleanup_temp_file(tmp_path)

    raw_resume_id = new_raw_resume_id()
    async with AsyncSessionLocal() as db:
        raw_resume = RawResume(
            id=raw_resume_id,
            raw_text=content,
            file_url=file_url or None,
            file_type=file_type or None,
            filename=filename or None,
            target_job_id=target_job_id or None,
            status=RawResumeStatus.PROCESSING,
        )
        db.add(raw_resume)
        await db.commit()

    return await _do_extract_and_link(raw_resume_id, content, auto_create=auto_create)


async def _handle_batch_parse(
    files: list[dict[str, Any]] | None = None,
    source: str = "upload",
    target_job_id: str = "",
) -> dict[str, Any]:
    """Batch parse multiple resumes."""
    if not files:
        return {"status": "failed", "error": {"code": "INVALID_INPUT", "message": "files list required"}}

    results = []
    failures = []
    for i, f in enumerate(files):
        try:
            content = f.get("content", "")
            if not content:
                failures.append({"index": i, "error": "empty content"})
                continue
            single = await _handle_parse_resume(
                content=content, target_job_id=target_job_id,
            )
            if single.get("status") == "success":
                results.append(single["data"])
            else:
                failures.append({"index": i, "error": single.get("error", {}).get("message", "unknown")})
        except Exception as e:
            failures.append({"index": i, "error": str(e)})

    return {
        "status": "success",
        "data": {
            "total": len(files),
            "success_count": len(results),
            "fail_count": len(failures),
            "results": results,
            "failures": failures,
        },
    }


async def _handle_retry_raw_resume(
    raw_resume_id: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """v0.5b: 重试解析失败的简历。raw_text 在 v0.4d 已落库，无需重新传文件。

    v0.6c.1: force 参数真正差异化语义
      - force=False (默认): _do_extract_and_link(reuse_candidate_id=True)
        → 复用 rr.candidate_id, svc.update() 更新原候选人 (raw_resumes.candidate_id 保持)
        → 旧候选人 ID 不变, 候选人字段被新解析结果覆盖
      - force=True: _do_extract_and_link(reuse_candidate_id=False)
        → 先清空 rr.candidate_id = None, 然后 svc.create() 创建新候选人
        → 旧候选人**不**自动删 (user 可手动 archive)

    状态校验：只接受 failed（processing/parsed 返 CONFLICT，不存在返 NOT_FOUND）。
    状态机：failed → processing → parsed/failed。
    """
    if not raw_resume_id:
        return {"status": "failed", "error": {"code": "INVALID_INPUT", "message": "raw_resume_id required"}}

    async with AsyncSessionLocal() as db:
        rr = await db.get(RawResume, raw_resume_id)
        if rr is None:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": f"raw_resume {raw_resume_id} not found"}}
        if rr.status == RawResumeStatus.PROCESSING:
            return {"status": "failed", "error": {"code": "CONFLICT", "message": "raw_resume 仍在处理中，请稍后再试"}}
        if rr.status == RawResumeStatus.PARSED:
            return {"status": "failed", "error": {"code": "CONFLICT", "message": "raw_resume 已解析成功，无需 retry"}}
        if rr.status != RawResumeStatus.FAILED:
            return {"status": "failed", "error": {"code": "CONFLICT", "message": f"无法 retry status={rr.status.value}"}}
        old_candidate_id = rr.candidate_id
        if force:
            rr.candidate_id = None
            logger.info(
                "retry force=True: cleared candidate_id=%s for raw_resume=%s (旧候选人留存待手动 archive)",
                old_candidate_id, raw_resume_id,
            )
        rr.status = RawResumeStatus.PROCESSING
        rr.error_message = None
        raw_text = rr.raw_text
        await db.commit()

    # v0.6c.1: force=False 调 reuse (svc.update 旧候选人), force=True 调 create (v0.6c 行为)
    return await _do_extract_and_link(
        raw_resume_id, raw_text, auto_create=True, reuse_candidate_id=not force
    )


async def _handle_parse_resume_async(
    content: str = "",
    file_url: str = "",
    file_type: str = "",
    filename: str = "",
    target_job_id: str = "",
    auto_create: bool = True,
) -> dict[str, Any]:
    """v0.6a: async version — 落 raw_resume + enqueue RQ task, 立刻返 task_id。

    不在 API 进程跑 LLM, worker 进程 (parse_worker) 跑 _do_extract_and_link。
    客户端 poll 走 poll_parse_resume 工具或 GET /raw-resumes/{id}/status。
    """
    from app.services.parse_task import enqueue_parse_task

    if not content and not file_url:
        return {"status": "failed", "error": {"code": "INVALID_INPUT", "message": "content or file_url required"}}

    raw_resume_id = new_raw_resume_id()
    async with AsyncSessionLocal() as db:
        rr = RawResume(
            id=raw_resume_id,
            raw_text=content or "",
            file_url=file_url or None,
            file_type=file_type or None,
            filename=filename or None,
            target_job_id=target_job_id or None,
            status=RawResumeStatus.PROCESSING,
        )
        db.add(rr)
        await db.commit()

    try:
        task_id = enqueue_parse_task(
            raw_resume_id=raw_resume_id,
            content=content or "",
            auto_create=auto_create,
        )
    except Exception as e:
        logger.error("Failed to enqueue parse task for %s: %s", raw_resume_id, e)
        async with AsyncSessionLocal() as db:
            stuck = await db.get(RawResume, raw_resume_id)
            if stuck is not None:
                stuck.status = RawResumeStatus.FAILED
                stuck.error_message = f"enqueue_failed: {e}"
                await db.commit()
        return {"status": "failed", "error": {"code": "QUEUE_UNAVAILABLE", "message": str(e), "retryable": True}}

    return {
        "status": "accepted",
        "data": {
            "raw_resume_id": raw_resume_id,
            "task_id": task_id,
            "poll_url": f"/raw-resumes/{raw_resume_id}/status",
        },
    }


async def _handle_poll_parse(raw_resume_id: str = "") -> dict[str, Any]:
    """v0.6a: poll task status by raw_resume_id.

    读 raw_resumes.status（_do_extract_and_link 写回, source of truth）。
    """
    from app.services.parse_task import poll_parse_task

    if not raw_resume_id:
        return {"status": "failed", "error": {"code": "INVALID_INPUT", "message": "raw_resume_id required"}}

    result = await poll_parse_task(raw_resume_id)
    if result is None:
        return {"status": "failed", "error": {"code": "NOT_FOUND", "message": f"raw_resume {raw_resume_id} not found"}}

    parse_status = result["status"]
    if parse_status == RawResumeStatus.PARSED.value:
        return {
            "status": "success",
            "data": {
                "raw_resume_id": result["raw_resume_id"],
                "parse_status": "parsed",
                "candidate_id": result["candidate_id"],
                "updated_at": result.get("updated_at"),
            },
        }
    if parse_status == RawResumeStatus.FAILED.value:
        return {
            "status": "failed",
            "error": {
                "code": "PARSE_FAILED",
                "message": result.get("error_message", "parse failed"),
                "retryable": True,
            },
            "data": {
                "raw_resume_id": result["raw_resume_id"],
                "parse_status": "failed",
            },
        }
    return {
        "status": "accepted",
        "data": {
            "raw_resume_id": result["raw_resume_id"],
            "parse_status": "processing",
            "updated_at": result.get("updated_at"),
        },
    }


async def _handle_get_profile(candidate_id: str = "") -> dict[str, Any]:
    """Get aggregated candidate profile."""
    if not candidate_id:
        return {"status": "failed", "error": {"code": "INVALID_INPUT", "message": "candidate_id required"}}

    async with AsyncSessionLocal() as db:
        svc = CandidateService(db)
        candidate = await svc.get_by_id(candidate_id)
        if not candidate:
            return {"status": "failed", "error": {"code": "NOT_FOUND", "message": "候选人不存在"}}

        return {
            "status": "success",
            "data": {
                "candidate_id": candidate.id,
                "basic_info": {
                    "name": mask_pii(candidate.name or ""),
                    "email": mask_pii(candidate.email or ""),
                    "phone": mask_pii(candidate.phone or ""),
                    "current_company": candidate.current_company or "",
                    "current_title": candidate.current_title or "",
                    "years_of_experience": candidate.experience_years,
                    "skills": candidate.skills or [],
                    "status": candidate.status.value if hasattr(candidate.status, "value") else str(candidate.status),
                },
                "created_at": candidate.created_at.isoformat() if candidate.created_at and hasattr(candidate.created_at, "isoformat") else str(candidate.created_at),
            },
        }


def _compute_quality(candidate: Any) -> int:
    score = 0
    if candidate.name:
        score += 15
    if candidate.email:
        score += 15
    if candidate.phone:
        score += 10
    if candidate.skills and len(candidate.skills) > 0:
        score += 20
    if candidate.experience_years:
        score += 20
    if candidate.education:
        score += 10
    if candidate.current_company:
        score += 5
    if candidate.current_title:
        score += 5
    return score


def _detect_red_flags(candidate: Any) -> list[dict]:
    flags = []
    if candidate.experience_years is not None and (candidate.experience_years or 0) < 1:
        flags.append({"type": "inexperienced", "severity": "info", "description": "工作经验不足1年"})
    return flags


tools = [
    {
        "type": "function",
        "function": {
            "name": "parse_resume",
            "description": "解析单份简历，提取结构化数据（联系方式、工作经历、技能、教育背景），评估质量评分，检测风险点，检查是否与现有候选人重复。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "简历文本内容（已有纯文本时使用）"},
                    "file_url": {"type": "string", "description": "简历文件URL（上传后的临时路径，优先使用）"},
                    "file_type": {"type": "string", "enum": ["pdf", "docx", "doc", "txt", "jpg", "png"], "description": "文件类型"},
                    "filename": {"type": "string", "description": "原始文件名（用于推断类型和临时文件名）"},
                    "target_job_id": {"type": "string", "description": "关联的职位ID（可选）"},
                    "auto_create": {"type": "boolean", "description": "解析成功后是否自动创建候选人（默认 True）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "batch_parse_resumes",
            "description": "批量解析多份简历，返回每份的结构化结果和失败列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string", "description": "简历文本"},
                                "filename": {"type": "string", "description": "文件名"},
                            },
                        },
                        "description": "简历文件列表",
                    },
                    "source": {"type": "string", "enum": ["upload", "email", "job_board", "linkedin"], "description": "简历来源"},
                    "target_job_id": {"type": "string", "description": "关联职位ID"},
                },
                "required": ["files"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_candidate_profile",
            "description": "获取已解析候选人的完整聚合画像，包括基本信息、技能、工作经历、面试记录等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "候选人ID"},
                },
                "required": ["candidate_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retry_raw_resume",
            "description": "重试解析失败的简历。raw_text 在 v0.4d 事务边界已落库，无需重新传文件。状态机：failed → processing → parsed/failed。v0.6c.1 force 参数真正差异化: False 复用旧 candidate_id 调 svc.update 候选人, True 清空 candidate_id 后 svc.create 新候选人（旧留存）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_resume_id": {"type": "string", "description": "raw_resumes 表的 ID（v0.4d parse_resume 返回的 raw_resume_id）"},
                    "force": {"type": "boolean", "description": "v0.6c.1: False (默认) 复用旧候选人调 svc.update, True 清空后 svc.create 新候选人。", "default": False},
                },
                "required": ["raw_resume_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_resume_async",
            "description": "v0.6a 异步版：落 raw_resume + enqueue RQ task, 立刻返 task_id, 不阻塞等待 LLM。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "简历文本内容"},
                    "file_url": {"type": "string", "description": "简历文件URL（v0.6a 暂只支持 content）"},
                    "file_type": {"type": "string", "description": "文件类型"},
                    "filename": {"type": "string", "description": "原始文件名"},
                    "target_job_id": {"type": "string", "description": "关联的职位ID"},
                    "auto_create": {"type": "boolean", "description": "解析成功后是否自动创建候选人（默认 True）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "poll_parse_resume",
            "description": "v0.6a 异步版：轮询 parse_resume_async 任务状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_resume_id": {"type": "string", "description": "parse_resume_async 返回的 raw_resume_id"},
                },
                "required": ["raw_resume_id"],
            },
        },
    },
]

handlers = {
    "parse_resume": _handle_parse_resume,
    "batch_parse_resumes": _handle_batch_parse,
    "get_candidate_profile": _handle_get_profile,
    "retry_raw_resume": _handle_retry_raw_resume,
    "parse_resume_async": _handle_parse_resume_async,
    "poll_parse_resume": _handle_poll_parse,
}
