"""文件下载与临时存储管理 — 供简历解析工具调用。"""

import logging
from app.core.logging import get_logger
import os
import tempfile
import uuid
from typing import Optional

logger = get_logger(__name__)


class ResumeDownloadError(Exception):
    """文件下载失败"""


async def download_file(url: str, timeout: float = 30.0) -> bytes:
    """从 URL 下载文件内容（支持 HTTP/HTTPS）。"""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()
            return response.content
    except httpx.TimeoutException:
        raise ResumeDownloadError(f"下载超时: {url}")
    except httpx.HTTPStatusError as e:
        raise ResumeDownloadError(f"下载失败 ({e.response.status_code}): {url}")
    except Exception as e:
        raise ResumeDownloadError(f"下载异常: {url} - {e}")


def get_temp_file_path(filename: str) -> str:
    """生成唯一的临时文件路径（保留原扩展名）。"""
    ext = os.path.splitext(filename)[1].lower() if filename else ""
    unique = uuid.uuid4().hex[:12]
    name = f"resume_{unique}{ext}"
    return os.path.join(tempfile.gettempdir(), name)


async def save_temp_file(content: bytes, filename: str) -> str:
    """保存字节内容到临时文件，返回文件路径。"""
    path = get_temp_file_path(filename)
    try:
        with open(path, "wb") as f:
            f.write(content)
        logger.debug("Saved temp file: %s (%.1f KB)", path, len(content) / 1024)
        return path
    except OSError as e:
        raise ResumeDownloadError(f"保存临时文件失败: {e}")


def cleanup_temp_file(path: str) -> None:
    """安全删除临时文件（不存在不报错）。"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
            logger.debug("Cleaned up temp file: %s", path)
    except OSError as e:
        logger.warning("Failed to cleanup temp file %s: %s", path, e)


def file_exists(path: str) -> bool:
    """检查文件是否存在。"""
    return bool(path and os.path.exists(path))


async def download_and_save(url: str, filename: str) -> str:
    """下载文件并保存到临时存储，返回路径。"""
    content = await download_file(url)
    return await save_temp_file(content, filename)
