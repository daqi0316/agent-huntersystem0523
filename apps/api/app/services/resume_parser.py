"""简历文件解析服务 — PDF / DOCX / TXT → 纯文本。"""

import io
import logging
import os

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


class ResumeParseError(Exception):
    """简历解析失败"""


def _parse_pdf(file_bytes: bytes) -> str:
    """用 PyMuPDF 提取 PDF 文本。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ResumeParseError("PyMuPDF 未安装")

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages: list[str] = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            pages.append(text.strip())
    doc.close()
    result = "\n\n".join(pages)
    if not result.strip():
        raise ResumeParseError("无法从 PDF 中提取文本（可能为扫描件）")
    return result


def _parse_docx(file_bytes: bytes) -> str:
    """用 python-docx 提取 DOCX 文本。"""
    try:
        from docx import Document
    except ImportError:
        raise ResumeParseError("python-docx 未安装")

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    result = "\n".join(paragraphs)
    if not result.strip():
        raise ResumeParseError("无法从 DOCX 中提取文本")
    return result


def _parse_txt(file_bytes: bytes) -> str:
    """直接读取 TXT（尝试 UTF-8 / GBK / latin-1）。"""
    for encoding in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return file_bytes.decode(encoding).strip()
        except (UnicodeDecodeError, UnicodeError):
            continue


def parse_resume(file_bytes: bytes, filename: str) -> str:
    """根据文件扩展名选择解析器，返回纯文本。"""
    ext = os.path.splitext(filename)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ResumeParseError(
            f"不支持的文件格式: {ext}，支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    logger.info("Parsing resume: %s (%.1f KB)", filename, len(file_bytes) / 1024)

    parsers = {
        ".pdf": _parse_pdf,
        ".docx": _parse_docx,
        ".doc": _parse_docx,
        ".txt": _parse_txt,
    }

    parser = parsers[ext]
    text = parser(file_bytes)

    # 基本清理
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = "\n".join(line for line in text.split("\n") if line)
    text = text.strip()

    if not text:
        raise ResumeParseError("解析结果为空")

    logger.info("Extracted %d characters from %s", len(text), filename)
    return text
