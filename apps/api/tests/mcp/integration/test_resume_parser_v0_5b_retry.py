"""v0.5b retry_raw_resume 工具测试。

覆盖：
  1. 主路径：failed → processing → parsed + candidate 创建
  2. NOT_FOUND：raw_resume_id 不存在
  3. CONFLICT：status=processing 不接受 retry
  4. CONFLICT：status=parsed 不接受 retry
  5. LLM 失败路径：retry 仍保持 status=FAILED + error_message 真值
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_retry_failed_resume_succeeds_and_links_candidate():
    """主路径：failed → processing → parsed + candidate 创建。"""
    from app.tools.resume_parser import _handle_retry_raw_resume
    from app.models.raw_resume import RawResumeStatus

    fake_candidate = MagicMock()
    fake_candidate.name = "张三"
    fake_candidate.email = "zhang@example.com"
    fake_candidate.phone = "13800000000"
    fake_candidate.skills = ["Python", "FastAPI"]
    fake_candidate.experience_years = 5
    fake_candidate.education = "清华大学"
    fake_candidate.current_company = "AC"
    fake_candidate.current_title = "Engineer"

    fake_created = MagicMock()
    fake_created.id = "cand-retry-1"

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw resume text"
    rr_retry.error_message = "low_confidence_or_extraction_error"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = None
    rr_extract.error_message = None

    call_count = {"n": 0}

    async def fake_get(model, id_):
        call_count["n"] += 1
        return rr_retry if call_count["n"] == 1 else rr_extract

    with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_db.get = AsyncMock(side_effect=fake_get)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = fake_candidate
            with patch("app.tools.resume_parser.CandidateService") as mock_svc_cls:
                mock_svc = MagicMock()
                mock_svc.create = AsyncMock(return_value=fake_created)
                mock_svc_cls.return_value = mock_svc

                result = await _handle_retry_raw_resume(raw_resume_id="rr-failed-1")

    assert result["status"] == "success"
    assert result["data"]["candidate_id"] == "cand-retry-1"
    assert rr_extract.status == RawResumeStatus.PARSED
    assert rr_extract.candidate_id == "cand-retry-1"


@pytest.mark.asyncio
async def test_retry_nonexistent_returns_NOT_FOUND():
    """retry 不存在的 raw_resume_id 返 NOT_FOUND。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=None)
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _handle_retry_raw_resume(raw_resume_id="rr-not-exists")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "NOT_FOUND"
    assert "not found" in result["error"]["message"].lower()


@pytest.mark.asyncio
async def test_retry_processing_resume_returns_CONFLICT():
    """retry processing 状态返 CONFLICT（不允许并发 retry 同一 raw_resume）。"""
    from app.tools.resume_parser import _handle_retry_raw_resume
    from app.models.raw_resume import RawResumeStatus

    rr_processing = MagicMock()
    rr_processing.status = RawResumeStatus.PROCESSING

    with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=rr_processing)
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _handle_retry_raw_resume(raw_resume_id="rr-processing-1")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "CONFLICT"
    assert "处理中" in result["error"]["message"]


@pytest.mark.asyncio
async def test_retry_parsed_resume_returns_CONFLICT():
    """retry parsed 状态返 CONFLICT（已成功无需 retry）。"""
    from app.tools.resume_parser import _handle_retry_raw_resume
    from app.models.raw_resume import RawResumeStatus

    rr_parsed = MagicMock()
    rr_parsed.status = RawResumeStatus.PARSED

    with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=rr_parsed)
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _handle_retry_raw_resume(raw_resume_id="rr-parsed-1")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "CONFLICT"
    assert "已解析" in result["error"]["message"]


@pytest.mark.asyncio
async def test_retry_llm_failure_keeps_status_failed():
    """retry 时 LLM 失败 → status 仍 FAILED + error_message 真值。"""
    from app.tools.resume_parser import _handle_retry_raw_resume
    from app.models.raw_resume import RawResumeStatus

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw resume text"
    rr_retry.error_message = "low_confidence_or_extraction_error"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = None
    rr_extract.error_message = None

    call_count = {"n": 0}

    async def fake_get(model, id_):
        call_count["n"] += 1
        return rr_retry if call_count["n"] == 1 else rr_extract

    with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_db.get = AsyncMock(side_effect=fake_get)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = None
            with patch("app.tools.resume_parser.CandidateService") as mock_svc_cls:
                mock_svc_cls.return_value = MagicMock()

                result = await _handle_retry_raw_resume(raw_resume_id="rr-failed-2")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LOW_CONFIDENCE"
    assert result["error"]["retryable"] is True
    assert rr_extract.status == RawResumeStatus.FAILED
    assert rr_extract.error_message == "low_confidence_or_extraction_error"
