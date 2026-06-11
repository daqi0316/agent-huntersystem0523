"""Tests for account_manager.py — 账号管理 + Cookie 加解密"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sourcing.account_manager import (
    AccountManager,
    BAN_THRESHOLD,
    LIMIT_THRESHOLD_PCT,
    decrypt_cookie,
    encrypt_cookie,
    mask_cookie,
)


class TestCookieCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        original = json.dumps([{"name": "session", "value": "abc123"}])
        encrypted = encrypt_cookie(original)
        assert encrypted != original
        decrypted = decrypt_cookie(encrypted)
        assert decrypted == original

    def test_mask_cookie_list_format(self):
        original = json.dumps([{"name": "session", "value": "secretvalue123"}])
        encrypted = encrypt_cookie(original)
        masked = mask_cookie(encrypted)
        assert "secretvalue123" not in masked
        assert "secr" in masked  # first 4 chars visible
        assert "23" in masked    # last 2 chars visible

    def test_mask_cookie_dict_format(self):
        original = json.dumps({"session": "abc123", "token": "xyz789"})
        encrypted = encrypt_cookie(original)
        masked = mask_cookie(encrypted)
        assert "<decrypted:" in masked

    def test_mask_cookie_encrypted_fallback(self):
        masked = mask_cookie("invalid-encrypted-data")
        assert masked == "<encrypted>"


class MockPlatformAccount:
    """Minimal mock for PlatformAccount model."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "id"):
            self.id = "acct-001"
        if not hasattr(self, "status"):
            self.status = "active"
        if not hasattr(self, "consecutive_failures"):
            self.consecutive_failures = 0
        if not hasattr(self, "daily_used"):
            self.daily_used = 0
        if not hasattr(self, "platform"):
            self.platform = "boss_zhipin"


class TestAccountManager:
    @pytest.fixture
    def manager(self):
        db = AsyncMock()
        redis = AsyncMock()
        return AccountManager(db=db, redis=redis)

    async def test_acquire_returns_active_account(self, manager):
        acct = MockPlatformAccount()
        manager._acquire_single = AsyncMock(return_value=acct)
        result = await manager.acquire("boss_zhipin")
        assert result is acct

    async def test_acquire_falls_through_to_next_type(self, manager):
        manager._acquire_single = AsyncMock(side_effect=[None, None, MockPlatformAccount()])
        result = await manager.acquire("boss_zhipin")
        assert result is not None
        assert manager._acquire_single.call_count == 3

    async def test_acquire_returns_none_when_all_exhausted(self, manager):
        manager._acquire_single = AsyncMock(return_value=None)
        result = await manager.acquire("boss_zhipin")
        assert result is None

    async def test_report_usage_increments_daily(self, manager):
        acct = MockPlatformAccount(daily_used=5, platform="boss_zhipin")
        manager._get_account = AsyncMock(return_value=acct)
        manager._get_daily_quota = AsyncMock(return_value=100)

        await manager.report_usage("acct-001", count=3)
        assert acct.daily_used == 8
        assert acct.consecutive_failures == 0
        manager.db.commit.assert_called_once()

    async def test_report_usage_marks_limited_when_over_threshold(self, manager):
        acct = MockPlatformAccount(daily_used=95, platform="boss_zhipin")
        manager._get_account = AsyncMock(return_value=acct)
        manager._get_daily_quota = AsyncMock(return_value=100)

        await manager.report_usage("acct-001", count=10)
        assert acct.daily_used == 105
        assert acct.status == "limited"

    async def test_report_usage_updates_redis_cache(self, manager):
        acct = MockPlatformAccount(daily_used=10, platform="boss_zhipin")
        manager._get_account = AsyncMock(return_value=acct)
        manager._get_daily_quota = AsyncMock(return_value=100)

        await manager.report_usage("acct-001", count=1)
        manager.redis.set.assert_called_once()

    async def test_rotate_increments_failures(self, manager):
        acct = MockPlatformAccount(consecutive_failures=2)
        manager._get_account = AsyncMock(return_value=acct)
        manager.acquire = AsyncMock(return_value=MockPlatformAccount())

        await manager.rotate("boss_zhipin", "acct-001")
        assert acct.consecutive_failures == 3

    async def test_rotate_bans_when_over_threshold(self, manager):
        acct = MockPlatformAccount(consecutive_failures=BAN_THRESHOLD - 1)
        manager._get_account = AsyncMock(return_value=acct)
        manager.acquire = AsyncMock(return_value=MockPlatformAccount())

        await manager.rotate("boss_zhipin", "acct-001")
        assert acct.status == "banned"
        assert acct.last_banned_at is not None

    async def test_rotate_clears_redis_cache(self, manager):
        acct = MockPlatformAccount(consecutive_failures=0)
        manager._get_account = AsyncMock(return_value=acct)
        manager.acquire = AsyncMock(return_value=MockPlatformAccount())
        manager.redis.keys.return_value = ["sourcing:account:boss_zhipin:acct-001:daily"]

        await manager.rotate("boss_zhipin", "acct-001")
        manager.redis.delete.assert_called_once()

    # ── _acquire_single ──

    async def test_acquire_single_selects_ordered(self, manager):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MockPlatformAccount(consecutive_failures=0, daily_used=50),
        ]
        manager.db.execute = AsyncMock(return_value=mock_result)
        manager._has_quota = AsyncMock(return_value=True)

        acct = await manager._acquire_single("boss_zhipin", "primary")
        assert acct is not None

    async def test_acquire_single_skips_quota_exceeded(self, manager):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MockPlatformAccount(daily_used=999),
        ]
        manager.db.execute = AsyncMock(return_value=mock_result)
        manager._has_quota = AsyncMock(return_value=False)

        acct = await manager._acquire_single("boss_zhipin", "primary")
        assert acct is None

    async def test_acquire_single_skips_banned_accounts(self, manager):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        manager.db.execute = AsyncMock(return_value=mock_result)

        acct = await manager._acquire_single("boss_zhipin", "primary")
        assert acct is None

    # ── _has_quota ──

    async def test_has_quota_uses_redis_cached_value(self, manager):
        acct = MockPlatformAccount(daily_used=10)
        manager._get_daily_quota = AsyncMock(return_value=100)
        manager.redis.get.return_value = b"95"  # Redis says 95 used

        result = await manager._has_quota(acct)
        assert result is True  # 95 < 100

    async def test_has_quota_falls_back_to_db(self, manager):
        acct = MockPlatformAccount(daily_used=50)
        manager._get_daily_quota = AsyncMock(return_value=100)
        manager.redis.get.return_value = None  # no cache

        result = await manager._has_quota(acct)
        assert result is True

    async def test_has_quota_no_limit(self, manager):
        acct = MockPlatformAccount(daily_used=999)
        manager._get_daily_quota = AsyncMock(return_value=0)

        result = await manager._has_quota(acct)
        assert result is True  # no quota limit

    async def test_has_quota_caches_in_redis(self, manager):
        acct = MockPlatformAccount(daily_used=30)
        manager._get_daily_quota = AsyncMock(return_value=100)
        manager.redis.get.return_value = None

        await manager._has_quota(acct)
        manager.redis.set.assert_called_once()

    # ── _get_daily_quota ──

    async def test_get_daily_quota_from_db(self, manager):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 200
        manager.db.execute = AsyncMock(return_value=mock_result)

        quota = await manager._get_daily_quota("boss_zhipin")
        assert quota == 200

    async def test_get_daily_quota_default(self, manager):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        manager.db.execute = AsyncMock(return_value=mock_result)

        quota = await manager._get_daily_quota("unknown_platform")
        assert quota == 300
