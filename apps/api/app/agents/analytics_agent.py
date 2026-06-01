"""AnalyticsAgent — 数据官。

使用 prompts/analytics.md 作为 system_prompt，
对报告生成提供 LLM 洞察，规则逻辑兜底。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.base import BaseAgent
from app.llm import get_llm_client

logger = logging.getLogger(__name__)

ANOMALY_THRESHOLDS = {
    "screen_rate": 20,
    "interview_rate": 15,
    "offer_rate": 10,
}


class AnalyticsAgent(BaseAgent):
    """数据分析 Agent — 漏斗、渠道、KPI、异常检测 (LLM + 规则兜底)。"""

    output_keys = ["funnel", "channel", "kpi", "anomaly"]

    def __init__(self, name: str = "analytics"):
        super().__init__(name)
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    # ── LLM 辅助 ──

    async def _llm_json_chat(self, user_prompt: str, temperature: float = 0.3, max_tokens: int = 2048) -> dict | None:
        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            reply = await self.llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
            if "```" in reply:
                parts = reply.split("```")
                for p in parts:
                    p = p.strip()
                    if p.startswith("{") or p.startswith("["):
                        reply = p
                        break
            start = reply.find("{")
            end = reply.rfind("}")
            if start != -1 and end != -1 and end > start:
                reply = reply[start: end + 1]
            return json.loads(reply)
        except Exception as e:
            logger.warning("AnalyticsAgent LLM call failed: %s", e)
            return None

    # ── 漏斗分析（规则驱动） ──

    def build_funnel(self, applied: int = 0, screened: int = 0, interviewed: int = 0, offered: int = 0, hired: int = 0) -> dict:
        """构建招聘漏斗。"""
        def rate(numerator: int, denominator: int) -> float:
            return round(numerator / denominator * 100, 1) if denominator > 0 else 0.0

        return {
            "funnel": {
                "applied": applied,
                "screened": screened,
                "interviewed": interviewed,
                "offered": offered,
                "hired": hired,
                "conversion_rates": {
                    "screen_rate": rate(screened, applied),
                    "interview_rate": rate(interviewed, screened),
                    "offer_rate": rate(offered, interviewed),
                    "hire_rate": rate(hired, offered),
                },
            }
        }

    # ── 渠道分析（规则驱动） ──

    def analyze_channels(self, channels: list[dict]) -> dict:
        """分析各渠道效果。"""
        analyzed = []
        total_apps = sum(c.get("applications", 0) for c in channels)

        for c in channels:
            name = c.get("name", "unknown")
            apps = c.get("applications", 0)
            cost = c.get("cost", 0)
            conversions = c.get("conversions", 0)
            conv_rate = round(conversions / apps * 100, 1) if apps > 0 else 0.0
            cost_per_app = round(cost / apps, 2) if apps > 0 else 0
            roi_label = "high"
            if cost_per_app > 100:
                roi_label = "low"
            elif cost_per_app > 50:
                roi_label = "medium"

            analyzed.append({
                "name": name,
                "applications": apps,
                "cost": cost,
                "conversion_rate": conv_rate,
                "cost_per_applicant": cost_per_app,
                "share_pct": round(apps / total_apps * 100, 1) if total_apps > 0 else 0,
                "roi": roi_label,
            })

        analyzed.sort(key=lambda x: x["cost_per_applicant"])
        return {"channels": analyzed}

    # ── KPI 计算（规则驱动） ──

    def calculate_kpi(
        self,
        time_to_fill_days: float = 0,
        offers_sent: int = 0,
        offers_accepted: int = 0,
        hires: int = 0,
        total_cost: float = 0,
        interviewed: int = 0,
        offered: int = 0,
    ) -> dict:
        """计算核心招聘 KPI。"""
        return {
            "kpi": {
                "time_to_fill_days": round(time_to_fill_days, 1),
                "offer_acceptance_rate": round(offers_accepted / offers_sent * 100, 1) if offers_sent > 0 else 0,
                "cost_per_hire": round(total_cost / hires, 2) if hires > 0 else 0,
                "interview_to_offer_ratio": round(offered / interviewed * 100, 1) if interviewed > 0 else 0,
            }
        }

    # ── 异常检测（规则驱动） ──

    def detect_anomalies(self, period_data: list[dict]) -> dict:
        """检测各渠道指标异常。"""
        anomalies = []
        for p in period_data:
            channel = p.get("name", "")
            for metric_key, threshold in ANOMALY_THRESHOLDS.items():
                current = p.get(metric_key, 0) or 0
                previous = p.get(f"{metric_key}_prev", 0) or 0
                if previous > 0:
                    drop_pct = round((previous - current) / previous * 100, 1)
                    if drop_pct >= threshold:
                        anomalies.append({
                            "channel": channel,
                            "metric": metric_key,
                            "drop_pct": drop_pct,
                            "threshold": threshold,
                            "alert": True,
                        })
        return {"anomalies": anomalies}

    # ── 全量报告（LLM 优先） ──

    async def generate_report(self, funnel_data: dict, channel_data: list[dict], kpi_data: dict) -> dict:
        """生成完整招聘分析报告（LLM 优先，规则兜底）。"""
        funnel = self.build_funnel(**funnel_data)
        channels = self.analyze_channels(channel_data)
        kpi = self.calculate_kpi(**kpi_data)
        anomalies = self.detect_anomalies(channel_data)

        if self.system_prompt:
            user_prompt = (
                f"请基于以下招聘数据分析生成洞察报告。\n\n"
                f"漏斗数据：{json.dumps(funnel, ensure_ascii=False)}\n"
                f"渠道数据：{json.dumps(channels, ensure_ascii=False)}\n"
                f"KPI 数据：{json.dumps(kpi, ensure_ascii=False)}\n"
                f"异常数据：{json.dumps(anomalies, ensure_ascii=False)}\n\n"
                f"输出 JSON：{{\n"
                f'  "report_summary": "一句话总结",\n'
                f'  "key_insights": ["洞察1", "洞察2"],\n'
                f'  "recommendations": ["建议1", "建议2"],\n'
                f'  "risk_flags": ["风险1"]\n'
                f"}}"
            )
            llm_out = await self._llm_json_chat(user_prompt)
            if llm_out and "report_summary" in llm_out:
                return {**funnel, **channels, **kpi, **anomalies, **llm_out}

        # 规则兜底
        return {
            **funnel, **channels, **kpi, **anomalies,
            "report_summary": (
                f"收到 {funnel['funnel']['applied']} 份申请，初筛通过 {funnel['funnel']['screened']} 人，"
                f"面试 {funnel['funnel']['interviewed']} 人，发出 {funnel['funnel']['offered']} 个 Offer，"
                f"入职 {funnel['funnel']['hired']} 人。发现 {len(anomalies['anomalies'])} 个异常。"
            ),
        }

    # ── 主入口 ──

    async def run(self, input_data: dict) -> dict:
        action = input_data.get("action", "funnel")
        summary_map = {
            "funnel": "招聘漏斗分析完成",
            "channels": "渠道效果分析完成",
            "kpi": "招聘 KPI 计算完成",
            "anomalies": "异常检测完成",
            "report": "全量报告生成完成",
        }

        if action == "funnel":
            result = self.build_funnel(
                applied=input_data.get("applied", 0),
                screened=input_data.get("screened", 0),
                interviewed=input_data.get("interviewed", 0),
                offered=input_data.get("offered", 0),
                hired=input_data.get("hired", 0),
            )
        elif action == "channels":
            result = self.analyze_channels(input_data.get("channels", []))
        elif action == "kpi":
            result = self.calculate_kpi(
                time_to_fill_days=input_data.get("time_to_fill_days", 0),
                offers_sent=input_data.get("offers_sent", 0),
                offers_accepted=input_data.get("offers_accepted", 0),
                hires=input_data.get("hires", 0),
                total_cost=input_data.get("total_cost", 0),
                interviewed=input_data.get("interviewed", 0),
                offered=input_data.get("offered", 0),
            )
        elif action == "anomalies":
            result = self.detect_anomalies(input_data.get("period_data", []))
        elif action == "report":
            result = await self.generate_report(
                funnel_data=input_data.get("funnel_data", {}),
                channel_data=input_data.get("channel_data", []),
                kpi_data=input_data.get("kpi_data", {}),
            )
        else:
            result = {"error": f"Unknown action: {action}", "available_actions": ["funnel", "channels", "kpi", "anomalies", "report"]}

        return self.format_result("completed", result, summary_map.get(action, f"分析 {action} 完成"))
