"""账号管理 — Cookie AES-256-GCM 加解密 / 配额跟踪 / 封号检测 / 故障轮换"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import select, and_

from app.sourcing.config import sourcing_settings
from app.sourcing.models.platform_account import AccountStatus, PlatformAccount

logger = logging.getLogger(__name__)

# Cookie 加密密钥（从环境变量读取，不存在则生成固定密钥用于开发）
_COOKIE_KEY = sourcing_settings.captcha_api_key or None
if _COOKIE_KEY:
    # 用 SHA256 派生 32 字节 → base64 → Fernet key
    import base64, hashlib
    _derived = hashlib.sha256(_COOKIE_KEY.encode()).digest()
    _FERNET_KEY = base64.urlsafe_b64encode(_derived)
else:
    # 开发环境固定密钥（仅用于本地测试）
    _FERNET_KEY = b"uB0lBxtHIG09gBkGPl3K3AhWWFyN4_Ce81GUgRldIeI="

_fernet = Fernet(_FERNET_KEY)

BAN_THRESHOLD = 5        # 连续失败次数 → 标记 banned
LIMIT_THRESHOLD_PCT = 90  # 配额使用率超过此值 → limited
REDIS_QUOTA_TTL = 86400   # 配额缓存 24h
REDIS_ACCOUNT_PREFIX = "sourcing:account:"


# ── Cookie 加解密 ──

def encrypt_cookie(cookie_json: str) -> str:
    """AES-256-GCM 加密 Cookie JSON"""
    return _fernet.encrypt(cookie_json.encode()).decode()


def decrypt_cookie(encrypted: str) -> str:
    """AES-256-GCM 解密 Cookie JSON"""
    return _fernet.decrypt(encrypted.encode()).decode()


def mask_cookie(encrypted: str) -> str:
    """脱敏显示（仅用于日志）"""
    try:
        raw = decrypt_cookie(encrypted)
        data = json.loads(raw)
        if isinstance(data, list):
            for c in data:
                if "value" in c:
                    v = c["value"]
                    c["value"] = v[:4] + "***" + v[-2:] if len(v) > 8 else "***"
            return json.dumps(data, ensure_ascii=False)
        return f"<decrypted:{len(raw)}chars>"
    except Exception:
        return "<encrypted>"


# ── 账号管理器 ──

class AccountManager:
    """平台账号管理 — 配额跟踪 / 故障轮换 / Cookie 加密存储"""

    def __init__(self, db, redis):
        self.db = db
        self.redis = redis

    async def acquire(self, platform: str) -> PlatformAccount | None:
        """获取一个可用账号

        优先级: primary > backup > crawl
        跳过: banned/expired/配额用完/连续失败超标
        """
        account_type_order = ["primary", "backup", "crawl"]
        for acct_type in account_type_order:
            account = await self._acquire_single(platform, acct_type)
            if account:
                return account
        return None

    async def report_usage(self, account_id: str, count: int = 1):
        """报告采集用量 → 增加 daily_used + 重置连续失败"""
        account = await self._get_account(account_id)
        if not account:
            logger.warning("report_usage: account %s not found", account_id)
            return

        account.daily_used += count
        account.consecutive_failures = 0

        # 检查配额阈值
        quota = await self._get_daily_quota(account.platform)
        pct = (account.daily_used / quota) * 100 if quota > 0 else 100
        if pct >= LIMIT_THRESHOLD_PCT and account.status == AccountStatus.ACTIVE.value:
            account.status = AccountStatus.LIMITED.value
            logger.info("Account %s quota %d%% → limited", account_id, int(pct))

        # 更新 Redis 配额缓存
        if self.redis:
            key = f"{REDIS_ACCOUNT_PREFIX}{account.platform}:{account_id}:daily"
            await self.redis.set(key, account.daily_used, ex=REDIS_QUOTA_TTL)

        await self.db.commit()

    async def rotate(self, platform: str, failed_account_id: str) -> PlatformAccount | None:
        """失败时标记 + 自动轮换到下一个可用账号"""
        account = await self._get_account(failed_account_id)
        if account:
            account.consecutive_failures += 1
            if account.consecutive_failures >= BAN_THRESHOLD:
                account.status = AccountStatus.BANNED.value
                account.last_banned_at = datetime.now(timezone.utc)
                logger.warning("Account %s banned (%d consecutive failures)",
                               failed_account_id, account.consecutive_failures)
            await self.db.commit()

        # 清除 Redis 缓存
        if self.redis:
            for key in await self.redis.keys(f"{REDIS_ACCOUNT_PREFIX}{platform}:*"):
                await self.redis.delete(key)

        return await self.acquire(platform)

    # ── 内部 ──

    async def _acquire_single(self, platform: str, account_type: str) -> PlatformAccount | None:
        result = await self.db.execute(
            select(PlatformAccount).where(
                and_(
                    PlatformAccount.platform == platform,
                    PlatformAccount.account_type == account_type,
                    PlatformAccount.is_active == True,
                    PlatformAccount.status == AccountStatus.ACTIVE.value,
                )
            ).order_by(PlatformAccount.consecutive_failures.asc())
        )
        accounts = list(result.scalars().all())
        for account in accounts:
            if await self._has_quota(account) and account.consecutive_failures < BAN_THRESHOLD:
                return account
        return None

    async def _has_quota(self, account: PlatformAccount) -> bool:
        """检查账号是否还有剩余日配额（Redis 缓存 → DB 兜底）"""
        quota = await self._get_daily_quota(account.platform)
        if quota <= 0:
            return True  # 没有限制

        used = account.daily_used
        if self.redis:
            key = f"{REDIS_ACCOUNT_PREFIX}{account.platform}:{account.id}:daily"
            cached = await self.redis.get(key)
            if cached is not None:
                used = int(cached)
            else:
                # 缓存 Redis 加速后续查询
                await self.redis.set(key, used, ex=REDIS_QUOTA_TTL)

        return used < quota

    async def _get_daily_quota(self, platform: str) -> int:
        """从 PlatformConfig 读取日配额（缓存友好）"""
        from app.sourcing.models.platform_config import PlatformConfig

        result = await self.db.execute(
            select(PlatformConfig.daily_quota_per_account)
            .where(PlatformConfig.name == platform)
        )
        row = result.scalar_one_or_none()
        return row if row is not None else 300

    async def _get_account(self, account_id: str) -> PlatformAccount | None:
        result = await self.db.execute(
            select(PlatformAccount).where(PlatformAccount.id == account_id)
        )
        return result.scalar_one_or_none()
