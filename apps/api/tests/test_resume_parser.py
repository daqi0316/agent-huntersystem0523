"""Tests for resume_parser — PDF/DOCX/TXT → plain text."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.services.resume_parser import (
    parse_resume,
    _parse_pdf,
    _parse_docx,
    _parse_txt,
    ResumeParseError,
)


class TestParseTxt:
    def test_utf8(self):
        text = "Hello 世界"
        assert _parse_txt(text.encode("utf-8")) == text

    def test_gbk_fallback(self):
        text = "简历测试"
        assert _parse_txt(text.encode("gbk")) == text

    def test_latin1_fallback(self):
        raw = b"Hello\xe9"
        result = _parse_txt(raw)
        assert "Hello" in result

    def test_replace_unknown(self):
        raw = b"\xff\xfe\x00\x01"
        result = _parse_txt(raw)
        assert isinstance(result, str)


class TestParseDocx:
    def _inject_docx(self, paragraph_texts):
        mock_paragraphs = [MagicMock(text=t) for t in paragraph_texts]
        mock_doc = MagicMock()
        mock_doc.paragraphs = mock_paragraphs
        mock_docx = MagicMock()
        mock_docx.Document.return_value = mock_doc
        sys.modules["docx"] = mock_docx

    def _cleanup_docx(self):
        sys.modules.pop("docx", None)

    def test_success(self):
        self._inject_docx(["Hello", "", "World"])
        try:
            result = _parse_docx(b"fake-docx")
            assert result == "Hello\nWorld"
        finally:
            self._cleanup_docx()

    def test_empty(self):
        self._inject_docx([])
        try:
            with pytest.raises(ResumeParseError, match="无法从 DOCX 中提取文本"):
                _parse_docx(b"")
        finally:
            self._cleanup_docx()

class TestParsePdf:
    def _inject_fitz(self, page_texts):
        mock_pages = [MagicMock(get_text=MagicMock(return_value=t)) for t in page_texts]
        mock_doc = MagicMock()
        mock_doc.__iter__.return_value = iter(mock_pages)
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc
        sys.modules["fitz"] = mock_fitz

    def _cleanup_fitz(self):
        sys.modules.pop("fitz", None)

    def test_success(self):
        self._inject_fitz(["Page text"])
        try:
            result = _parse_pdf(b"fake-pdf")
            assert "Page text" in result
        finally:
            self._cleanup_fitz()

    def test_empty_pdf(self):
        self._inject_fitz([])
        try:
            with pytest.raises(ResumeParseError, match="无法从 PDF 中提取文本"):
                _parse_pdf(b"")
        finally:
            self._cleanup_fitz()

    def test_only_blank_pages(self):
        self._inject_fitz(["   "])
        try:
            with pytest.raises(ResumeParseError, match="无法从 PDF 中提取文本"):
                _parse_pdf(b"")
        finally:
            self._cleanup_fitz()

class TestParseResume:
    def test_txt(self):
        result = parse_resume(b"Hello World", "resume.txt")
        assert result == "Hello World"

    def test_unsupported_extension(self):
        with pytest.raises(ResumeParseError, match="不支持的文件格式"):
            parse_resume(b"data", "resume.xyz")

    def test_empty_after_cleanup_raises(self):
        with pytest.raises(ResumeParseError, match="解析结果为空"):
            parse_resume(b"  \n  \n  ", "resume.txt")

    def test_docx_delegates(self):
        mock_paragraphs = [MagicMock(text="Content")]
        mock_doc = MagicMock()
        mock_doc.paragraphs = mock_paragraphs
        mock_docx_mod = MagicMock()
        mock_docx_mod.Document.return_value = mock_doc
        sys.modules["docx"] = mock_docx_mod
        try:
            result = parse_resume(b"fake", "resume.docx")
            assert "Content" in result
        finally:
            sys.modules.pop("docx", None)
