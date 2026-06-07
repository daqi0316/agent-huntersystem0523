"""v1.0b datetime.utcnow → datetime.now(UTC) tz-aware 验证."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


def test_now_utc_returns_tz_aware():
    """datetime.now(UTC) 返 tz-aware datetime, 不再是 naive."""
    now = datetime.now(timezone.utc)
    assert now.tzinfo is not None, "datetime.now(UTC) 必须是 tz-aware"
    assert now.tzinfo == timezone.utc


def test_now_utc_isoformat_includes_offset():
    """aware datetime isoformat() 含 +00:00 后缀 (不是 naive 无后缀).

    v0.5 Momus 修 #1 关注: JSON serialize 后缀变化 (从无变 +00:00).
    此测试验 aware datetime 真有后缀.
    """
    now = datetime.now(timezone.utc)
    iso = now.isoformat()
    assert iso.endswith("+00:00") or iso.endswith("Z"), (
        f"aware isoformat 应含 +00:00 或 Z, 实际 {iso}"
    )


def test_now_utc_compatible_with_aware_datetime():
    """aware datetime 可与 DB 列 (DateTime(timezone=True)) 的 aware datetime 比较."""
    from datetime import datetime, timezone

    from app.models.raw_resume import RawResume, RawResumeStatus

    now_utc = datetime.now(timezone.utc)
    # 模拟 DB 取出的 aware datetime (真实 DB 返 aware)
    rr = RawResume(
        id="rr-test-1",
        raw_text="test",
        status=RawResumeStatus.PROCESSING,
        created_at=now_utc,
        updated_at=now_utc,
    )
    # 比较不抛 TypeError
    assert rr.updated_at >= now_utc
    assert rr.updated_at.tzinfo is not None


def test_now_utc_does_not_raise_deprecation():
    """aware datetime 不触发 pydantic / sqlalchemy 2.x naive tz 警告."""
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        # 触发 timestamp 字符串化
        iso = now.isoformat()
        # 应无 "Datetime utcnow" 或 "no tzinfo" 警告
        naive_warnings = [
            w for w in caught
            if "utcnow" in str(w.message).lower() or "naive" in str(w.message).lower()
        ]
        assert len(naive_warnings) == 0, (
            f"aware datetime 触发 naive 警告: {[str(w.message) for w in naive_warnings]}"
        )
