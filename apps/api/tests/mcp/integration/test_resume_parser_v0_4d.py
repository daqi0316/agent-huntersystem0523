"""v0.4d 事务边界测试 — resume_parser raw_resume 表

验证：
  1. LLM 成功 → raw_resumes.status=parsed + candidate_id 链
  2. LLM 失败 → raw_resumes.status=failed + error_message 落库
  3. raw_text 在 LLM 之前就落库（事务边界）
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_v0_4d_llm_failure_preserves_raw_text():
    """v0.4d 关键：LLM 解析失败时 raw_text 仍在 raw_resumes 表（status=failed）。"""
    from app.tools.resume_parser import _handle_parse_resume

    with patch("app.tools.resume_parser.new_raw_resume_id", return_value="rr-test-1"):
        with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
                mock_extract.return_value = None

                result = await _handle_parse_resume(content="raw resume text here")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LOW_CONFIDENCE"
    assert result["error"]["retryable"] is True
    assert result["data"]["raw_resume_id"] == "rr-test-1", "raw_resume_id 应返回供 retry"
    assert "raw resume text" in result["data"]["raw_text_snippet"]

    add_calls = mock_db.add.call_args_list
    assert len(add_calls) >= 1, "raw_resume 至少 add 一次（事务边界第一落）"

    commit_calls = mock_db.commit.call_args_list
    assert len(commit_calls) >= 2, (
        "raw_resume 先 commit (status=processing)，"
        "LLM 失败后再 commit (status=failed) — 至少 2 次 commit"
    )


@pytest.mark.asyncio
async def test_v0_4d_llm_success_does_not_crash_and_creates_raw_resume():
    """v0.4d: LLM 成功路径不崩溃，raw_resume 落库（事务边界前 commit）。
    详细 candidate_id / basic_info 验证由 test_resume_parser.py 集成测覆盖。
    """
    from app.tools.resume_parser import _handle_parse_resume

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
    fake_created.id = "cand-1"

    with patch("app.tools.resume_parser.new_raw_resume_id", return_value="rr-test-2"):
        with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
            def session_factory():
                db = AsyncMock()
                db.add = MagicMock()
                db.commit = AsyncMock()
                db.get = AsyncMock()
                return db

            mock_session_cls.return_value.__aenter__ = AsyncMock(side_effect=session_factory)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
                mock_extract.return_value = fake_candidate
                with patch("app.services.candidate.CandidateService") as mock_svc_cls:
                    mock_svc = MagicMock()
                    mock_svc.create = AsyncMock(return_value=fake_created)
                    mock_svc_cls.return_value = mock_svc

                    try:
                        result = await _handle_parse_resume(content="raw text")
                        assert result is not None
                    except Exception as e:
                        pytest.fail(f"LLM 成功路径崩溃: {e}")


@pytest.mark.asyncio
async def test_v0_4d_raw_text_saved_before_llm_call():
    """v0.4d 关键顺序：raw_resume add() 必须在 LLM 调用之前发生（事务边界）。"""
    from app.tools.resume_parser import _handle_parse_resume

    call_order: list[str] = []

    with patch("app.tools.resume_parser.AsyncSessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_db.add = MagicMock(side_effect=lambda x: call_order.append("add_raw_resume"))
        mock_db.commit = AsyncMock(side_effect=lambda: call_order.append("commit"))
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("app.tools.resume_parser.extract_from_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.side_effect = lambda *a, **kw: call_order.append("llm_call") or (_ for _ in ()).throw(
                RuntimeError("llm failed")
            )
            with patch("app.services.candidate.CandidateService") as mock_svc_cls:
                mock_svc_cls.return_value.create = AsyncMock()

                try:
                    await _handle_parse_resume(content="test")
                except Exception:
                    pass

    assert "add_raw_resume" in call_order
    llm_idx = call_order.index("llm_call")
    add_idx = call_order.index("add_raw_resume")
    assert add_idx < llm_idx, f"raw_resume add 必须在 LLM 之前（add={add_idx}, llm={llm_idx}）"
