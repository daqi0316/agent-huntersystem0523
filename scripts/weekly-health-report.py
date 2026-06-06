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

        from app.api.dashboard_growth import (
            _cac_by_channel, _churn_30d, _customer_count, _ltv_by_plan,
            _nps_score, _referral_summary,
        )
        cac = await _cac_by_channel(db)
        churn = await _churn_30d(db)
        ltv = await _ltv_by_plan(db)
        nps = await _nps_score(db)
        referral = await _referral_summary(db)
        customers = await _customer_count(db)
        growth_report = format_growth_report(customers, cac, ltv, churn, nps, referral)
        logger.info("growth report:\n%s", growth_report)
        await send_feishu(growth_report)


def format_growth_report(customers, cac, ltv, churn, nps, referral) -> str:
    lines = ["📈 增长周报 (内部)", ""]
    lines.append(f"👥 客户总数: {customers['total']}")
    lines.append(f"  by_status: {customers['by_status']}")
    lines.append(f"  by_plan: {customers['by_plan']}")
    lines.append("")
    lines.append(f"🔄 30d churn: {churn['churned_30d']} 个 ({churn['churn_rate_pct']}%)")
    lines.append("")
    lines.append("💰 30d LTV by plan:")
    for plan, data in ltv.items():
        lines.append(f"  • {plan}: ¥{data.get('revenue_cents', 0) / 100:.2f} ({data.get('order_count', 0)} 单)")
    lines.append("")
    lines.append("👥 老带新:")
    lines.append(f"  codes={referral['total_codes']} uses={referral['total_uses']} 转化率={referral['conversion_rate_pct']}%")
    lines.append("")
    lines.append("📊 CAC by channel (mock P6-1/6-8 真实接入后):")
    for ch, data in cac.items():
        lines.append(f"  • {ch}: ¥{data['cost_cny']} / {data['new_customers']} 客")
    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(run())
