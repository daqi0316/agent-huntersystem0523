"""OfferingAgent — 谈判专家。

使用 prompts/offering.md 作为 system_prompt，
对 Offer 函生成和谈判策略提供 LLM 驱动，规则逻辑兜底。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.base import BaseAgent
from app.llm import get_llm_client

logger = logging.getLogger(__name__)

DEFAULT_BENCHMARK = {
    "p25": 0,
    "p50": 0,
    "p75": 0,
    "source": "内置参考数据（建议接入市场薪酬数据库）",
}

NEGOTIATION_SCENARIOS = {
    "competing_offer": {"label": "竞品 Offer", "strategy": "加急流程 + 签字费", "max_adjustment_pct": 15},
    "expectation_too_high": {"label": "期望过高", "strategy": "强调成长空间 + 福利", "max_adjustment_pct": 5},
    "hesitating": {"label": "犹豫不决", "strategy": "安排与团队交流", "max_adjustment_pct": 0},
    "interested": {"label": "已有意向", "strategy": "加快流程 + 适当让步", "max_adjustment_pct": 5},
    "key_talent": {"label": "关键人才", "strategy": "特批流程，突破上限需审批", "max_adjustment_pct": 20},
}


class OfferingAgent(BaseAgent):
    """薪酬 Agent — 定薪、定级、Offer 生成 (LLM + 规则兜底)。"""

    output_keys = ["benchmark", "offer_package", "equity_tips", "negotiation_tips"]

    def __init__(self, name: str = "offering"):
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
            logger.warning("OfferingAgent LLM call failed: %s", e)
            return None

    # ── 薪酬基准 ──

    def get_salary_benchmark(self, role: str, location: str = "") -> dict:
        return {"role": role, "location": location or "默认市场", **DEFAULT_BENCHMARK}

    # ── 总包计算 ──

    def calculate_total_package(self, base: float, bonus_pct: float = 15.0, equity_yearly: float = 0, benefits: float = 5000) -> dict:
        bonus = base * (bonus_pct / 100)
        total = base + bonus + equity_yearly + benefits
        return {"base": base, "bonus": round(bonus, 2), "bonus_pct": bonus_pct, "equity_yearly": equity_yearly, "benefits": benefits, "total_package": round(total, 2)}

    # ── Offer 函生成（LLM 优先） ──

    async def generate_offer_letter(self, candidate_name: str, title: str, company: str, package: dict, start_date: str) -> dict:
        """生成 Offer 函（LLM 优先，模板兜底）。"""
        if self.system_prompt:
            pkg_str = "\n".join(f"  - {k}: {v}" for k, v in package.items())
            user_prompt = (
                f"请生成 Offer 函。\n\n"
                f"候选人：{candidate_name}\n职位：{title}\n公司：{company}\n"
                f"入职日期：{start_date}\n薪酬包：\n{pkg_str}\n\n"
                f"输出 JSON：{{\n"
                f'  "candidate_name": "...",\n'
                f'  "title": "...",\n'
                f'  "company": "...",\n'
                f'  "start_date": "...",\n'
                f'  "package": {{...}},\n'
                f'  "offer_letter": "完整 Offer 函正文",\n'
                f'  "status": "draft"\n'
                f"}}"
            )
            llm_out = await self._llm_json_chat(user_prompt, temperature=0.4, max_tokens=2048)
            if llm_out and "offer_letter" in llm_out:
                return llm_out

        # 模板兜底
        letter = (
            f"尊敬的 {candidate_name}，\n\n"
            f"我们很高兴代表 {company} 向您发送以下 Offer：\n\n"
            f"职位：{title}\n入职日期：{start_date}\n薪资结构：\n"
            f"  - 基本薪资：¥{package.get('base', 0):,.2f}/年\n"
            f"  - 绩效奖金：{package.get('bonus_pct', 0)}%（约 ¥{package.get('bonus', 0):,.2f}）\n"
            f"  - 股权/期权：¥{package.get('equity_yearly', 0):,.2f}/年\n"
            f"  - 其他福利：¥{package.get('benefits', 0):,.2f}/年\n"
            f"  - 总包合计：¥{package.get('total_package', 0):,.2f}/年\n\n"
            f"详细福利说明及入职指引将在确认后另行发送。\n\n"
            f"期待您的加入！\n{company} 招聘团队"
        )
        return {"candidate_name": candidate_name, "title": title, "company": company, "start_date": start_date, "package": package, "offer_letter": letter, "status": "draft"}

    # ── 谈判策略（LLM 优先） ──

    async def recommend_negotiation_strategy(self, scenario: str, current_package: dict | None = None) -> dict:
        """推荐谈判策略（LLM 优先，规则兜底）。"""
        if self.system_prompt:
            pkg_str = str(current_package or {})
            user_prompt = (
                f"请推荐谈判策略。\n\n"
                f"场景：{scenario}\n当前薪酬包：{pkg_str}\n\n"
                f"输出 JSON：{{\n"
                f'  "scenario": "...",\n'
                f'  "approach": "策略描述",\n'
                f'  "max_adjustment_pct": 10,\n'
                f'  "adjusted_total": 0,\n'
                f'  "talking_points": ["话术要点"]\n'
                f"}}"
            )
            llm_out = await self._llm_json_chat(user_prompt, temperature=0.4, max_tokens=1024)
            if llm_out and "approach" in llm_out:
                return llm_out

        # 规则兜底
        scenario_key = scenario if scenario in NEGOTIATION_SCENARIOS else "interested"
        config = NEGOTIATION_SCENARIOS[scenario_key]
        package = current_package or {}
        adjusted = round(package.get("total_package", 0) * (1 + config["max_adjustment_pct"] / 100), 2) if package and config["max_adjustment_pct"] > 0 else None
        return {"scenario": config["label"], "approach": config["strategy"], "max_adjustment_pct": config["max_adjustment_pct"], "adjusted_total": adjusted}

    # ── 风险评估（规则驱动） ──

    def assess_risk(self, candidate_name: str, package: dict, scenario: str = "") -> dict:
        risk_factors = []
        total = package.get("total_package", 0)
        bonus_pct = package.get("bonus_pct", 0)
        if total > 1000000:
            risk_factors.append("总包超过百万，需高层审批")
        if bonus_pct > 30:
            risk_factors.append("奖金比例偏高，可能影响内部公平性")
        if scenario == "competing_offer":
            risk_factors.append("竞品 Offer 场景，需加速流程")
        if scenario == "key_talent":
            risk_factors.append("关键人才，离职影响大")
        level = "high" if len(risk_factors) >= 3 else ("medium" if len(risk_factors) >= 1 else "low")
        rec = "建议提交审批" if level == "high" else ("建议与用人部门确认" if level == "medium" else "按标准流程推进")
        return {"candidate": candidate_name, "risk_level": level, "risk_factors": risk_factors, "recommendation": rec}

    # ── 主入口 ──

    async def run(self, input_data: dict) -> dict:
        action = input_data.get("action", "calculate")
        summary_map = {
            "benchmark": "薪酬基准查询完成",
            "calculate": "薪酬总包计算完成",
            "offer_letter": "Offer 函生成完成",
            "negotiation": "谈判策略推荐完成",
            "risk_assessment": "风险评估完成",
        }

        if action == "benchmark":
            result = self.get_salary_benchmark(role=input_data.get("role", ""), location=input_data.get("location", ""))
        elif action == "calculate":
            result = self.calculate_total_package(base=input_data.get("base", 0), bonus_pct=input_data.get("bonus_pct", 15), equity_yearly=input_data.get("equity_yearly", 0), benefits=input_data.get("benefits", 5000))
        elif action == "offer_letter":
            result = await self.generate_offer_letter(candidate_name=input_data.get("candidate_name", ""), title=input_data.get("title", ""), company=input_data.get("company", ""), package=input_data.get("package", {}), start_date=input_data.get("start_date", ""))
        elif action == "negotiation":
            result = await self.recommend_negotiation_strategy(scenario=input_data.get("scenario", "interested"), current_package=input_data.get("current_package"))
        elif action == "risk_assessment":
            result = self.assess_risk(candidate_name=input_data.get("candidate_name", ""), package=input_data.get("package", {}), scenario=input_data.get("scenario", ""))
        else:
            result = {"error": f"Unknown action: {action}", "available_actions": ["benchmark", "calculate", "offer_letter", "negotiation", "risk_assessment"]}

        return self.format_result("completed", result, summary_map.get(action, f"定薪 {action} 完成"))
