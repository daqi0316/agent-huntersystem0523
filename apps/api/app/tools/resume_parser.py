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
from app.services.resume_extractor import extract_from_text
from app.services.candidate import CandidateService

logger = logging.getLogger(__name__)


async def _handle_parse_resume(
    content: str = "",
    file_url: str = "",
    file_type: str = "",
    filename: str = "",
    target_job_id: str = "",
    auto_create: bool = True,
) -> dict[str, Any]:
    """Parse a single resume: extract structured data, assess quality, detect duplicates."""
    if not content and not file_url:
        return {"status": "failed", "error": {"code": "INVALID_INPUT", "message": "content or file_url required"}}

    # ── 文件下载：file_url → 临时文件 → 解析 ────────────────────────
    if file_url and not content:
        from app.tools.file_parser import download_and_save, cleanup_temp_file
        from app.services.resume_parser import parse_resume as _parse_resume_file, ResumeParseError

        tmp_path = None
        try:
            # 生成临时文件名（保留扩展名）
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

    candidate = None
    try:
        candidate = await extract_from_text(content)
    except Exception as e:
        logger.warning("LLM extraction failed: %s", e)
        candidate = None

    if candidate is None or not candidate.email:
        return {
            "status": "failed",
            "error": {"code": "LOW_CONFIDENCE", "message": "解析置信度过低，无法提取有效信息", "retryable": True},
            "data": {"raw_text_snippet": content[:500]},
        }

    candidate_id = ""
    if auto_create:
        try:
            from app.schemas.candidate import CandidateCreate
            async with AsyncSessionLocal() as db:
                svc = CandidateService(db)
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
            logger.warning("Auto-create candidate failed (non-blocking): %s", e)

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
]

handlers = {
    "parse_resume": _handle_parse_resume,
    "batch_parse_resumes": _handle_batch_parse,
    "get_candidate_profile": _handle_get_profile,
}
