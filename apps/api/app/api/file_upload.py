"""临时文件上传 API — 供 Agent 聊天中的简历上传调用。"""

import logging

from fastapi import APIRouter, UploadFile, File

from app.core.response import error
from app.tools._file_parser_helpers import save_temp_file, ResumeDownloadError

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
SUPPORTED_TYPES = {"pdf", "docx", "doc", "txt", "jpg", "png"}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传临时文件，返回 file_url 供 Agent 工具下载。"""
    if not file.filename:
        return error("文件名不能为空", status_code=400)

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in SUPPORTED_TYPES:
        return error(
            f"不支持的文件格式 '.{ext}'，支持: {', '.join(sorted(SUPPORTED_TYPES))}",
            status_code=400,
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        return error("文件为空", status_code=400)
    if len(file_bytes) > MAX_FILE_SIZE:
        return error(f"文件过大，最大支持 {MAX_FILE_SIZE // 1024 // 1024}MB", status_code=400)

    try:
        file_path = await save_temp_file(file_bytes, file.filename)
    except ResumeDownloadError as e:
        return error(f"文件保存失败: {e}", status_code=500)

    return {
        "file_url": file_path,
        "filename": file.filename,
        "file_size": len(file_bytes),
    }
