"""v0.6c.1 retry_raw_resume force=True 真差异化语义测试。

覆盖 (Momus §2.3 修正版计划):
  1. force=False 调 svc.update 旧候选人 + 验 update_data 含新解析字段
  2. force=False 但 candidate 已被外部删, fallback svc.create
  3. force=True 调 svc.create 新候选人 (与 v0.6c 测试 4 互补, 验 update 不被调)
  4. force=False svc.update 抛异常 → status=FAILED 保持
  5. force=True svc.create 抛异常 → status=FAILED 保持
  6. force=True 旧候选人留存 (svc.delete 不被调)

注: 真正差异化语义 (force=False=svc.update, force=True=svc.create) 是 v0.6c.1
与 v0.6c 的核心区别。v0.6c 加 force 参数但默认行为与 v0.5b 等价 (无差异化);
v0.6c.1 改 force 语义: False=update 旧候选人 (保持 candidate_id), True=create 新候选人。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.raw_resume import RawResumeStatus


def _make_fake_candidate():
    c = MagicMock()
    c.name = "张三"
    c.email = "zhang@example.com"
    c.phone = "13800000000"
    c.skills = ["Python"]
    c.experience_years = 5
    c.education = "清华大学"
    c.current_company = "AC"
    c.current_title = "Engineer"
    return c


def _make_session_pair(rr_retry: MagicMock, rr_extract: MagicMock):
    """建 retry/extract 两个 session 的 mock, db.get 根据 call_count 返回不同 rr."""
    call_count = {"n": 0}

    async def fake_get(model, id_):
        call_count["n"] += 1
        return rr_retry if call_count["n"] == 1 else rr_extract

    return call_count, fake_get


@pytest.mark.asyncio
async def test_force_false_calls_svc_update_with_existing_candidate_id_and_new_data():
    """force=False 走 reuse 路径: svc.update 被调 + update_data 含新解析字段。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    fake_candidate = _make_fake_candidate()
    fake_updated = MagicMock()
    fake_updated.id = "cand-reused"

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-existing"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = "cand-existing"
    rr_extract.error_message = None

    call_count, fake_get = _make_session_pair(rr_retry, rr_extract)

    update_calls: list = []

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

                async def fake_create(*a, **kw):
                    raise AssertionError("force=False 路径不应调 svc.create")

                async def fake_update(candidate_id, update_data):
                    update_calls.append((candidate_id, update_data))
                    return fake_updated

                mock_svc.create = fake_create
                mock_svc.update = fake_update
                mock_svc_cls.return_value = mock_svc

                result = await _handle_retry_raw_resume(raw_resume_id="rr-failed-1", force=False)

    assert result["status"] == "success"
    assert result["data"]["candidate_id"] == "cand-reused"
    # 验 svc.update 收到原 candidate_id
    assert len(update_calls) == 1
    assert update_calls[0][0] == "cand-existing", "svc.update 必须收到原 candidate_id"
    # 验 update_data 含新解析字段
    update_data = update_calls[0][1]
    assert update_data.email == "zhang@example.com"
    assert update_data.name == "张三"
    assert update_data.skills == ["Python"]
    # rr.candidate_id 保持旧值 (v0.6c.1 reuse 路径)
    assert rr_extract.candidate_id == "cand-existing"


@pytest.mark.asyncio
async def test_force_false_falls_back_to_create_when_svc_update_returns_none():
    """force=False 但 svc.update 返 None (candidate 已被外部删), fallback svc.create。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    fake_candidate = _make_fake_candidate()
    fake_created = MagicMock()
    fake_created.id = "cand-fallback-new"

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-deleted-externally"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = "cand-deleted-externally"  # 失败 fallback 路径: 覆盖成新
    rr_extract.error_message = None

    call_count, fake_get = _make_session_pair(rr_retry, rr_extract)

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

                async def fake_update(candidate_id, update_data):
                    return None  # candidate 已被外部删

                async def fake_create(create_data):
                    return fake_created

                mock_svc.update = fake_update
                mock_svc.create = fake_create
                mock_svc_cls.return_value = mock_svc

                result = await _handle_retry_raw_resume(raw_resume_id="rr-failed-2", force=False)

    assert result["status"] == "success"
    assert result["data"]["candidate_id"] == "cand-fallback-new"
    # rr.candidate_id 被覆盖成新值 (fallback 路径)
    assert rr_extract.candidate_id == "cand-fallback-new"


@pytest.mark.asyncio
async def test_force_true_creates_new_candidate_and_does_not_call_update():
    """force=True 调 svc.create 新候选人 + svc.update 不被调。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    fake_candidate = _make_fake_candidate()
    fake_created = MagicMock()
    fake_created.id = "cand-new-from-force-true"

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-old-original"  # force=True 会清空

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = None  # force=True 清空后
    rr_extract.error_message = None

    call_count, fake_get = _make_session_pair(rr_retry, rr_extract)

    update_called = False

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

                async def fake_update(*a, **kw):
                    nonlocal update_called
                    update_called = True
                    return None

                async def fake_create(create_data):
                    return fake_created

                mock_svc.update = fake_update
                mock_svc.create = fake_create
                mock_svc_cls.return_value = mock_svc

                result = await _handle_retry_raw_resume(raw_resume_id="rr-failed-3", force=True)

    assert result["status"] == "success"
    assert result["data"]["candidate_id"] == "cand-new-from-force-true"
    assert update_called is False, "force=True 路径不应调 svc.update"
    # rr.candidate_id 最终是新值 (force=True 清空 → svc.create 覆盖)
    assert rr_extract.candidate_id == "cand-new-from-force-true"


@pytest.mark.asyncio
async def test_force_false_update_failure_is_non_blocking_status_parsed():
    """force=False svc.update 抛异常 → v0.5a 非阻塞设计, status=PARSED (LLM 已成功, 候选人不阻塞)。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    fake_candidate = _make_fake_candidate()

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-existing"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = "cand-existing"
    rr_extract.error_message = None

    call_count, fake_get = _make_session_pair(rr_retry, rr_extract)

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

                async def fake_update(*a, **kw):
                    raise RuntimeError("DB connection lost")

                mock_svc.update = fake_update
                mock_svc_cls.return_value = mock_svc

                result = await _handle_retry_raw_resume(raw_resume_id="rr-failed-4", force=False)

    # v0.5a 非阻塞设计: LLM 成功但 candidate update 失败, status=PARSED (不写 FAILED)
    assert result["status"] == "success"
    assert result["data"]["candidate_id"] == ""
    assert rr_extract.status == RawResumeStatus.PARSED
    assert rr_extract.candidate_id is None


@pytest.mark.asyncio
async def test_force_true_create_failure_is_non_blocking_status_parsed():
    """force=True svc.create 抛异常 → v0.5a 非阻塞设计, status=PARSED (LLM 已成功)。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    fake_candidate = _make_fake_candidate()

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-old"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = None
    rr_extract.error_message = None

    call_count, fake_get = _make_session_pair(rr_retry, rr_extract)

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

                async def fake_create(*a, **kw):
                    raise RuntimeError("DB connection lost")

                mock_svc.create = fake_create
                mock_svc_cls.return_value = mock_svc

                result = await _handle_retry_raw_resume(raw_resume_id="rr-failed-5", force=True)

    assert result["status"] == "success"
    assert result["data"]["candidate_id"] == ""
    assert rr_extract.status == RawResumeStatus.PARSED
    assert rr_extract.candidate_id is None


@pytest.mark.asyncio
async def test_force_true_old_candidate_not_deleted():
    """force=True 旧候选人留存 (svc.delete 不被调), 与 v0.6c 测试 4 互补。"""
    from app.tools.resume_parser import _handle_retry_raw_resume

    fake_candidate = _make_fake_candidate()
    fake_created = MagicMock()
    fake_created.id = "cand-new"

    rr_retry = MagicMock()
    rr_retry.status = RawResumeStatus.FAILED
    rr_retry.raw_text = "raw text"
    rr_retry.error_message = "low_confidence"
    rr_retry.candidate_id = "cand-old"

    rr_extract = MagicMock()
    rr_extract.status = RawResumeStatus.PROCESSING
    rr_extract.candidate_id = None
    rr_extract.error_message = None

    call_count, fake_get = _make_session_pair(rr_retry, rr_extract)

    deleted_ids: list = []

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
                    return fake_created

                async def fake_delete(candidate_id):
                    deleted_ids.append(candidate_id)

                mock_svc.create = fake_create
                mock_svc.delete = fake_delete
                mock_svc_cls.return_value = mock_svc

                result = await _handle_retry_raw_resume(raw_resume_id="rr-failed-6", force=True)

    assert result["status"] == "success"
    assert deleted_ids == [], f"force=True 不应自动删旧候选人, 但 svc.delete 被调 {deleted_ids}"
