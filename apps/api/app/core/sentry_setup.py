"""P5-7: Sentry 接入 (backend + frontend hooks)。

backend: sentry-sdk FastAPI 集成, trace LLM/HTTP。
frontend: Sentry.init 在客户端 (next.config.js) 注入 DSN。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def init_sentry() -> bool:
    """启动时调一次。无 SENTRY_DSN 就跳过 (本地 dev 不阻塞)。"""
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        logger.info("SENTRY_DSN not set, Sentry disabled")
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.asyncio import AsyncioIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENV", "production"),
            release=os.getenv("GIT_SHA", "unknown"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
                AsyncioIntegration(),
            ],
            before_send=_scrub_pii,
        )
        logger.info("Sentry initialized: env=%s release=%s", os.getenv("SENTRY_ENV"), os.getenv("GIT_SHA"))
        return True
    except ImportError:
        logger.warning("sentry-sdk not installed, skipping")
        return False
    except Exception as e:
        logger.error("Sentry init failed: %s", e)
        return False


def _scrub_pii(event, hint):
    """before_send 钩子: 脱敏 PII (email/手机/姓名) 不上报。"""
    try:
        if "request" in event and "data" in event["request"]:
            for k in ("email", "name", "phone", "mobile", "address"):
                if k in event["request"]["data"]:
                    event["request"]["data"][k] = "[redacted]"
        if "user" in event and "email" in event["user"]:
            event["user"]["email"] = "[redacted]"
        if "extra" in event:
            for k in ("password", "hashed_password", "wechat_unionid", "wechat_openid"):
                if k in event["extra"]:
                    event["extra"][k] = "[redacted]"
    except Exception:
        pass
    return event
