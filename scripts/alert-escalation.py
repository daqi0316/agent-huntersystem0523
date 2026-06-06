#!/usr/bin/env python3
"""P5-7: 告警升级路径 (cron 每 5min 跑一次)。

逻辑:
- 调 telemetry.check_alerts() 看当前触发
- P1 5min 无 ack → 升级到 PM (飞书 @)
- P1 30min 无 ack → 阿里云工单 + 客户群公告
- P2 仅首次通知, 不升级

ack 机制: /privacy/alerts/ack endpoint (P5-7 ship 后) 或 redis SET。
本脚本无 ack 持久化 (Phase 4 简化版): 仅 "X 分钟前是否发过同样告警", 防止重复打扰。
"""
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("alert_escalation")

# 简单持久化: 文件记录最近 ack 时间
ACK_FILE = Path("/var/lib/ai-recruitment/alert_acks.json")
ACK_TTL_SECONDS = {
    "P1": 300,   # 5min
    "P2": 1800,  # 30min
}


def _load_acks() -> dict:
    if not ACK_FILE.exists():
        return {}
    try:
        with open(ACK_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_acks(acks: dict) -> None:
    ACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ACK_FILE, "w") as f:
        json.dump(acks, f, indent=2)


def _alert_key(alert: dict) -> str:
    return hashlib.md5(
        f"{alert['name']}|{alert.get('actual_value', '')}".encode()
    ).hexdigest()[:16]


async def escalate():
    from app.core.telemetry import run_alert_check_cycle, check_alerts
    from app.core.sentry_setup import init_sentry
    init_sentry()

    alerts = await check_alerts()
    if not alerts:
        logger.info("no alerts triggered")
        return 0

    acks = _load_acks()
    now = time.time()
    new_alerts = []
    for alert in alerts:
        key = _alert_key(alert)
        last_sent = acks.get(key, {}).get("sent_at", 0)
        ttl = ACK_TTL_SECONDS.get(alert["severity"], 300)
        if now - last_sent < ttl:
            continue
        new_alerts.append(alert)
        acks[key] = {
            "name": alert["name"],
            "severity": alert["severity"],
            "sent_at": now,
            "triggered_at": alert["triggered_at"],
        }

    if not new_alerts:
        logger.info("all alerts in cooldown")
        _save_acks(acks)
        return 0

    sent = 0
    for alert in new_alerts:
        from app.core.telemetry import send_feishu_alert
        ok = await send_feishu_alert(alert)
        if ok:
            sent += 1
            logger.warning(
                "alert sent: %s severity=%s actual=%s",
                alert["name"], alert["severity"], alert["actual_value"],
            )
        else:
            logger.error("alert send failed: %s", alert["name"])

    _save_acks(acks)
    return sent


if __name__ == "__main__":
    sys.exit(asyncio.run(escalate()) or 0)
