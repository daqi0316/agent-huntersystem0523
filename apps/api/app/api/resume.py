"""简历导入 API — 上传 → 解析 → LLM 抽取 → 确认创建候选人。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.llm.omlx_client import OMLXClient
from app.schemas.candidate import CandidateCreate
from app.schemas.resume import (
    ResumeUploadResponse,
    ResumeExtractResponse,
    ResumeConfirmCreate,
    ResumeConfirmResponse,
    ExtractedCandidate,
)
from app.services.candidate import CandidateService
from app.services.resume_parser import parse_resume, ResumeParseError
from app.services.resume_extractor import extract_from_text

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload-resume", response_model=ResumeUploadResponse)
async def upload_resume(file: UploadFile = File(...)):
    """Step 1: 上传简历文件，解析为纯文本。"""
    if not file.filename:
        raise HTTPException(400, detail="文件名不能为空")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    supported = {"pdf", "docx", "doc", "txt"}
    if ext not in supported:
        raise HTTPException(
            400,
            detail=f"不支持的文件格式 '.{ext}'，支持: {', '.join(sorted(supported))}",
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(400, detail="文件为空")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(400, detail=f"文件过大，最大支持 {MAX_FILE_SIZE // 1024 // 1024}MB")

    try:
        plain_text = parse_resume(file_bytes, file.filename)
    except ResumeParseError as e:
        raise HTTPException(422, detail=str(e))

    return ResumeUploadResponse(
        filename=file.filename,
        file_size=len(file_bytes),
        text_length=len(plain_text),
        plain_text=plain_text,
    )


@router.post("/extract-resume", response_model=ResumeExtractResponse)
async def extract_resume(file: UploadFile = File(...)):
    """Step 2: 上传 + 解析 + LLM 结构化抽取，一步到位。"""
    if not file.filename:
        raise HTTPException(400, detail="文件名不能为空")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(400, detail=f"文件过大，最大支持 {MAX_FILE_SIZE // 1024 // 1024}MB")

    try:
        plain_text = parse_resume(file_bytes, file.filename)
    except ResumeParseError as e:
        raise HTTPException(422, detail=str(e))

    try:
        candidate = await extract_from_text(plain_text)
        needs_review = False
    except Exception as e:
        logger.warning("LLM extraction failed, using fallback: %s", e)
        candidate = ExtractedCandidate(raw_text=plain_text)
        needs_review = True

    return ResumeExtractResponse(
        filename=file.filename,
        text_length=len(plain_text),
        candidate=candidate,
        needs_review=needs_review,
    )


@router.post("/confirm-resume", response_model=ResumeConfirmResponse)
async def confirm_resume(
    body: ResumeConfirmCreate,
    db: AsyncSession = Depends(get_db),
):
    """Step 3: 确认抽取结果，创建候选人（可选运行 AI 初筛）。"""
    parsed = body.parsed

    if not parsed.email:
        raise HTTPException(422, detail="邮箱不能为空，请手动补充")

    # 创建候选人
    create_data = CandidateCreate(
        name=parsed.name or parsed.email.split("@")[0],
        email=parsed.email,
        phone=parsed.phone or None,
        summary=parsed.summary or None,
        skills=parsed.skills or [],
        experience_years=parsed.experience_years,
        education=parsed.education or None,
        current_company=parsed.current_company or None,
        current_title=parsed.current_title or None,
    )

    service = CandidateService(db)
    try:
        candidate = await service.create(create_data)
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(409, detail=f"该邮箱已存在候选人: {parsed.email}")
        raise HTTPException(500, detail=f"创建候选人失败: {e}")

    screening_result = None
    if body.run_screening and body.job_id:
        try:
            from app.services.screening import ScreeningService

            screening = ScreeningService()
            sr = await screening.screen_resume(
                candidate_id=candidate.id,
                job_id=body.job_id,
                resume_text=parsed.raw_text,
                job_requirements="",
            )
            screening_result = sr
        except Exception as e:
            logger.warning("Screening after import failed: %s", e)

    return ResumeConfirmResponse(
        candidate_id=candidate.id,
        candidate_name=candidate.name,
        screening_result=screening_result,
        message=f"候选人 '{candidate.name}' 创建成功"
        + ("，AI 初筛已完成。" if screening_result else "。"),
    )
