#!/usr/bin/env python3
"""P5-15: 周报 cron — 每周一 09:00 推飞书健康度排行。

用法: python scripts/weekly-health-report.py
挂载: 0 9 * * 1 (cron)
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("weekly_health_report")

from app.core.database import AsyncSessionLocal
from app.services.onboarding import compute_health_score, list_all_health_scores
from app.models.onboarding import RiskLevel


def format_report(rows: list) -> str:
    if not rows:
        return "📊 周报: 暂无客户数据"
    by_risk = {"high_risk": [], "at_risk": [], "healthy": []}
    for r in rows:
        by_risk[r.risk_level].append(r)

    lines = ["📊 客户健康度周报 (每周一推送)", ""]

    for level, label, emoji in [
        ("high_risk", "🔴 高风险 (< 50)", "🔴"),
        ("at_risk", "🟡 需关注 (50-70)", "🟡"),
        ("healthy", "🟢 健康 (≥ 70)", "🟢"),
    ]:
        items = by_risk[level]
        if not items:
            continue
        lines.append(f"{emoji} {label} ({len(items)} 个)")
        for r in items[:5]:
            lines.append(f"  • {r.org_id[:12]}... 评分 {r.total_score:.1f}")
        if len(items) > 5:
            lines.append(f"  ... 还有 {len(items) - 5} 个")
        lines.append("")

    avg = sum(r.total_score for r in rows) / len(rows) if rows else 0
    lines.append(f"📈 整体均值: {avg:.1f}")
    lines.append(f"📊 总客户数: {len(rows)}")
    return "\n".join(lines)


async def send_feishu(text: str) -> bool:
    webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
    if not webhook:
        logger.warning("FEISHU_WEBHOOK_URL not set, report suppressed")
        return False
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook, json={
                "msg_type": "text",
                "content": {"text": text},
            })
            return resp.status_code == 200
    except Exception as e:
        logger.error("feishu send failed: %s", e)
        return False


async def run():
    async with AsyncSessionLocal() as db:
        rows = await list_all_health_scores(db)
        for r in rows:
            try:
                await compute_health_score(db, r.org_id)
            except Exception as e:
                logger.warning("refresh %s failed: %s", r.org_id, e)
        rows = await list_all_health_scores(db)
        report = format_report(rows)
        logger.info("report:\n%s", report)
        await send_feishu(report)


if __name__ == "__main__":
    asyncio.run(run())
