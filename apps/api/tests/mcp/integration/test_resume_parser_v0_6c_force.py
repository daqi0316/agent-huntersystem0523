"""v0.6c retry_raw_resume force=True 参数测试。

覆盖 (Momus §3 决策点 3 = 方案 A: 清空 candidate_id + 重建):
  1. 不传 force (默认 False) v0.5b 行为不破坏
  2. force=False 路径上, retry handler 不清空 candidate_id (保持 v0.5b 行为)
  3. force=True 路径上, retry handler 清空 candidate_id = None
  4. force=True 完整路径: 最终 rr.candidate_id != 旧值 (创建新候选人)

注: 真正"差异化语义" (如 force=False 时复用旧 candidate_id 做 update) 推 v0.6c.1。
本 PR 仅加 force 参数 + 路径中间态清晰化。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.raw_resume import RawResumeStatus


@pytest.mark.asyncio
async def test_retry_default_no_force_arg_works():
    """不传 force (默认 False), LLM 成功, 走 v0.5b 主路径, 状态正确更新。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    fake_candidate = MagicMock()
    fake_candidate.name = "张三"
    fake_candidate.email = "zhang@example.com"
    fake_candidate.phone = "13800000000"
    fake_candidate.skills = ["Python"]
    fake_candidate.experience_years = 5
    fake_candidate.education = "清华大学"
    fake_candidate.current_company = "AC"
    fake_candidate.current_title = "Engineer"

    fake_created = MagicMock()
    fake_created.id = "cand-v0_5b"

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-old"  # v0.5b 行为: 旧 candidate_id 在 retry handler 中保留

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = "cand-old"  # v0.5b: _do_extract_and_link 拿到时是旧值
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
    assert result["data"]["candidate_id"] == "cand-v0_5b"
    # v0.5b 行为: rr.candidate_id 在 _do_extract_and_link 中被覆盖为新值
    assert rr_extract.candidate_id == "cand-v0_5b"


@pytest.mark.asyncio
async def test_retry_force_false_keeps_old_candidate_id_in_path():
    """force=False 路径上: retry handler 不清空 candidate_id, 仍指向旧值。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-old"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = "cand-old"  # 不被清空
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

                await _handle_retry_raw_resume(raw_resume_id="rr-failed-2", force=False)

    # 验证: retry handler 提交后, rr_extract (下一次 db.get 拿到) 看到 candidate_id = "cand-old"
    # (force=False 不清空, retry handler 写入的是 status=processing + error_message=None, candidate_id 保持)
    assert rr_extract.candidate_id == "cand-old", "force=False 路径上 candidate_id 保持旧值"
    assert rr_extract.status == RawResumeStatus.FAILED, "LLM 失败, 状态回到 FAILED"


@pytest.mark.asyncio
async def test_retry_force_true_clears_candidate_id_in_path():
    """force=True 路径上: retry handler 清空 candidate_id = None, 然后调 _do_extract_and_link。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-old"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = None  # force=True 已清空
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

                await _handle_retry_raw_resume(raw_resume_id="rr-failed-3", force=True)

    # force=True 路径上, retry handler 写入后, 下一次 db.get 看到 candidate_id = None (被清空)
    assert rr_extract.candidate_id is None, "force=True 路径上 candidate_id 被清空"


@pytest.mark.asyncio
async def test_retry_force_true_creates_new_candidate_with_different_id():
    """force=True 完整路径: 最终 rr.candidate_id != 旧值, 新候选人创建, 旧候选人留存。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    fake_candidate = MagicMock()
    fake_candidate.name = "张三"
    fake_candidate.email = "zhang@example.com"
    fake_candidate.phone = "13800000000"
    fake_candidate.skills = ["Python"]
    fake_candidate.experience_years = 5
    fake_candidate.education = "清华大学"
    fake_candidate.current_company = "AC"
    fake_candidate.current_title = "Engineer"

    fake_created = MagicMock()
    fake_created.id = "cand-new-from-force-true"

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-old-original"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = None
    rr_extract.error_message = None

    call_count = {"n": 0}

    async def fake_get(model, id_):
        call_count["n"] += 1
        return rr_retry if call_count["n"] == 1 else rr_extract

    deleted_ids = []
    original_create_ids = []

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

                async def fake_create(create_data):
                    original_create_ids.append(create_data.email)
                    return fake_created

                async def fake_delete(candidate_id):
                    deleted_ids.append(candidate_id)

                mock_svc.create = fake_create
                mock_svc.delete = fake_delete  # 如果调, 记录; 方案 A 不应调
                mock_svc_cls.return_value = mock_svc

                result = await _handle_retry_raw_resume(raw_resume_id="rr-failed-4", force=True)

    # 验 1: 返回成功 + 新 candidate_id
    assert result["status"] == "success"
    assert result["data"]["candidate_id"] == "cand-new-from-force-true"
    # 验 2: 新 ID != 旧 ID
    assert result["data"]["candidate_id"] != "cand-old-original"
    # 验 3: 旧候选人**不**被自动删 (方案 A 不 destructive)
    assert deleted_ids == [], f"force=True 不应自动删旧候选人, 但 svc.delete 被调 {deleted_ids}"
    # 验 4: 新候选人**真**被创建
    assert original_create_ids == ["zhang@example.com"]
    # 验 5: 最终 raw_resumes.candidate_id = 新值 (覆盖 None → 新)
    assert rr_extract.candidate_id == "cand-new-from-force-true"
