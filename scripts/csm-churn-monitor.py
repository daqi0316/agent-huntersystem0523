#!/usr/bin/env python3
"""P6-12: CSM churn 监控 cron — 每日 09:00 跑, 飞书 + 1-on-1 任务。

用法: python scripts/csm-churn-monitor.py
挂载: 0 9 * * *
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("csm_churn_monitor")

from app.core.database import AsyncSessionLocal
from app.services.csm import detect_churn_risks, format_csm_alert


async def send_feishu(text: str) -> bool:
    webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
    if not webhook:
        logger.warning("FEISHU_WEBHOOK_URL not set, alert suppressed")
        return False
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook, json={
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": "🚨 CSM 任务提醒"}},
                    "elements": [
                        {"tag": "markdown", "content": text}
                    ],
                },
            })
            return resp.status_code == 200
    except Exception as e:
        logger.error("feishu send failed: %s", e)
        return False


async def run():
    async with AsyncSessionLocal() as db:
        tasks = await detect_churn_risks(db)
        logger.info("detected %d new CSM tasks", len(tasks))
        for t in tasks:
            logger.info("  - [%s] %s %s: %s", t.severity.value, t.type.value, t.org_id, t.title)
        if tasks:
            alert = format_csm_alert(tasks)
            await send_feishu(alert)
        else:
            logger.info("no new tasks today")


if __name__ == "__main__":
    asyncio.run(run())
