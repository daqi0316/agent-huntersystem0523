"""Tests for resume_extractor — LLM text → structured candidate data."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.resume_extractor import extract_from_text, _fallback_extract
from app.schemas.resume import ExtractedCandidate


class TestExtractFromText:
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.chat = AsyncMock()
        return llm

    async def test_success(self, mock_llm):
        mock_llm.chat.return_value = (
            '{"name": "张三", "email": "zhang@test.com", "phone": "13800138000", '
            '"summary": "Senior dev", "skills": ["Python", "AWS"], '
            '"experience_years": 5, "education": "本科", '
            '"current_company": "Acme", "current_title": "Engineer"}'
        )
        result = await extract_from_text("张三简历内容", llm=mock_llm)
        assert isinstance(result, ExtractedCandidate)
        assert result.name == "张三"
        assert result.email == "zhang@test.com"
        assert result.skills == ["Python", "AWS"]
        assert result.experience_years == 5

    async def test_markdown_code_block(self, mock_llm):
        mock_llm.chat.return_value = (
            "```json\n"
            '{"name": "李四", "email": "li@test.com"}\n'
            "```"
        )
        result = await extract_from_text("李四简历", llm=mock_llm)
        assert result.name == "李四"
        assert result.email == "li@test.com"

    async def test_json_prefix(self, mock_llm):
        mock_llm.chat.return_value = (
            'json\n{"name": "王五", "email": "wang@test.com"}'
        )
        result = await extract_from_text("王五简历", llm=mock_llm)
        assert result.name == "王五"

    async def test_partial_data_uses_empty_defaults(self, mock_llm):
        mock_llm.chat.return_value = '{"name": "赵六"}'
        result = await extract_from_text("赵六简历", llm=mock_llm)
        assert result.name == "赵六"
        assert result.email == ""
        assert result.skills == []
        assert result.experience_years is None

    async def test_invalid_json_falls_back_to_regex(self, mock_llm):
        mock_llm.chat.return_value = "一些没有JSON的文本"
        result = await extract_from_text("联系邮箱: test@foo.com 电话: 13800138001", llm=mock_llm)
        assert result.email == "test@foo.com"
        assert result.phone == "13800138001"

    async def test_auto_create_llm_when_none(self):
        """Line 44: OMLXClient created automatically when llm=None."""
        with patch("app.services.resume_extractor.OMLXClient") as MockOMLX:
            mock_instance = AsyncMock()
            mock_instance.chat = AsyncMock(return_value='{"name": "Auto"}')
            MockOMLX.return_value = mock_instance

            result = await extract_from_text("简历文本", llm=None)
            assert isinstance(result, ExtractedCandidate)
            assert result.name == "Auto"
            MockOMLX.assert_called_once()

    async def test_regex_match_but_json_invalid(self, mock_llm):
        """Lines 74-77: regex match finds JSON-like text but it's invalid."""
        mock_llm.chat.return_value = '{"name": "Bot", "skills": [broken}'
        result = await extract_from_text("Python, Java", llm=mock_llm)
        assert isinstance(result, ExtractedCandidate)
        assert "python" in result.skills or "java" in result.skills

    async def test_llm_returns_junk_falls_back_to_keyword(self, mock_llm):
        mock_llm.chat.return_value = "纯垃圾文本无结构"
        result = await extract_from_text("熟悉Python和Docker", llm=mock_llm)
        assert "python" in result.skills
        assert "docker" in result.skills


class TestFallbackExtract:
    def test_email_extraction(self):
        data = _fallback_extract("联系我: foo.bar@example.com.cn")
        assert data["email"] == "foo.bar@example.com.cn"

    def test_phone_mobile(self):
        data = _fallback_extract("电话: 13912345678")
        assert data["phone"] == "13912345678"

    def test_phone_landline(self):
        data = _fallback_extract("电话: 010-12345678")
        assert data["phone"] == "010-12345678"

    def test_skill_keywords(self):
        data = _fallback_extract("熟悉 Python, Java, Docker, Kubernetes")
        assert "python" in data["skills"]
        assert "java" in data["skills"]
        assert "docker" in data["skills"]

    def test_empty_text(self):
        data = _fallback_extract("")
        assert data["name"] == ""
        assert data["email"] == ""
        assert data["skills"] == []
