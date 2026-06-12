"""Prompt-B: SourcingAgent — 猎手。

能力:
- 人才 Mapping：目标公司分析、竞品团队识别（LLM + 规则兜底）
- 渠道策略：渠道效果分析、预算分配建议
- 触达话术：个性化沟通模板（LLM + 模板兜底）
- JD 生成（代理至 JDGeneratorService）
- 被动候选人激活、在库推荐
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.base import BaseAgent
from app.llm import get_llm_client

logger = logging.getLogger(__name__)

SOURCE_CHANNELS = {
    "linkedin": {"cost_per_applicant": 80, "typical_roi": "medium"},
    "bosspy": {"cost_per_applicant": 30, "typical_roi": "high"},
    "mianjing": {"cost_per_applicant": 50, "typical_roi": "medium"},
    "referral": {"cost_per_applicant": 20, "typical_roi": "high"},
    "campus": {"cost_per_applicant": 40, "typical_roi": "low"},
    "headhunter": {"cost_per_applicant": 200, "typical_roi": "medium"},
}


class SourcingAgent(BaseAgent):
    """猎头/寻源 Agent — JD 生成 + 人才 Mapping + 渠道策略 (LLM + 规则兜底)。"""

    output_keys = ["candidates", "jd", "talent_map", "templates", "recommendations"]

    def __init__(self, name: str = "sourcing"):
        super().__init__(name)
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    # ── LLM 辅助函数 ──

    async def _llm_json_chat(self, user_prompt: str, temperature: float = 0.3, max_tokens: int = 2048) -> dict | None:
        """调用 LLM 并解析 JSON 响应。返回 None 表示失败。"""
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
            logger.warning("LLM JSON call failed: %s", e)
            return None

    # ── 人才 Mapping（LLM 优先） ──

    async def build_talent_map(self, target_companies: list[str], target_roles: list[str]) -> dict:
        """生成目标公司人才 Mapping 建议（LLM 优先，规则兜底）。"""
        if self.system_prompt:
            user_prompt = (
                f"请为以下需求生成人才 Mapping 方案：\n"
                f"目标公司：{', '.join(target_companies)}\n"
                f"目标岗位：{', '.join(target_roles)}\n\n"
                f"输出 JSON 格式：{{\n"
                f'  "talent_map": [{{"company": "公司名", "target_roles": ["岗位"], "key_hiring_signals": ["信号"], "priority": "high|medium|low"}}],\n'
                f'  "total_targets": 0,\n'
                f'  "coverage_strategy": "触达策略描述"\n'
                f"}}"
            )
            llm_result = await self._llm_json_chat(user_prompt)
            if llm_result and "talent_map" in llm_result:
                return llm_result

        # 规则兜底
        companies = []
        for company in target_companies:
            companies.append({
                "company": company,
                "target_roles": target_roles,
                "key_hiring_signals": [f"{company} 近期融资/扩张/关键岗位更替"],
                "priority": "high",
            })
        return {
            "talent_map": companies,
            "total_targets": len(companies),
            "coverage_strategy": "按公司优先级分批触达，A 轮后公司优先",
        }

    # ── 渠道策略（LLM 优先） ──

    async def recommend_channels(self, budget: float, priority_roles: list[str]) -> dict:
        """基于预算和目标角色推荐渠道分配（LLM 优先，规则兜底）。"""
        if self.system_prompt:
            channels_str = "\n".join(
                f"- {k}: 单候选人成本 ¥{v['cost_per_applicant']}, ROI {v['typical_roi']}"
                for k, v in SOURCE_CHANNELS.items()
            )
            user_prompt = (
                f"总预算：¥{budget}\n"
                f"重点岗位：{', '.join(priority_roles)}\n\n"
                f"可选渠道：\n{channels_str}\n\n"
                f"输出 JSON 格式：{{\n"
                f'  "total_budget": {budget},\n'
                f'  "priority_roles": [...],\n'
                f'  "recommendations": [{{\n'
                f'    "channel": "渠道名", "budget_pct": 百分比, "budget_amount": 金额,\n'
                f'    "cost_per_applicant": 0, "expected_roi": "high|medium|low"\n'
                f"  }}]\n"
                f"}}"
            )
            llm_result = await self._llm_json_chat(user_prompt)
            if llm_result and "recommendations" in llm_result:
                return llm_result

        # 规则兜底
        recommendations = []
        for channel, info in SOURCE_CHANNELS.items():
            cost = info["cost_per_applicant"]
            pct = max(5, int(100 / (cost / 50)))
            recommendations.append({
                "channel": channel,
                "budget_pct": min(pct, 40),
                "cost_per_applicant": cost,
                "expected_roi": info["typical_roi"],
            })
        total_pct = sum(r["budget_pct"] for r in recommendations)
        if total_pct > 0:
            for r in recommendations:
                r["budget_pct"] = round(r["budget_pct"] / total_pct * 100, 1)
        for r in recommendations:
            r["budget_amount"] = round(budget * r["budget_pct"] / 100, 2)
        return {"total_budget": budget, "priority_roles": priority_roles, "recommendations": recommendations}

    # ── 触达话术（LLM 优先） ──

    async def generate_outreach(
        self,
        candidate_name: str,
        company: str,
        role: str,
        personal_note: str = "",
    ) -> dict:
        """生成个性化触达话术（LLM 优先，模板兜底）。"""
        if self.system_prompt:
            user_prompt = (
                f"请为以下候选人生成个性化触达话术：\n"
                f"候选人：{candidate_name}\n"
                f"当前公司：{company}\n"
                f"当前岗位：{role}\n"
                f"个人亮点：{personal_note or '行业经验'}\n\n"
                f"输出 JSON 格式：{{\n"
                f'  "candidate": "{candidate_name}",\n'
                f'  "templates": [{{\n'
                f'    "target_profile": "描述",\n'
                f'    "subject": "邮件主题",\n'
                f'    "template": "话术正文",\n'
                f'    "suggested_channel": "linkedin|email|wechat",\n'
                f'    "timing": "建议发送时间"\n'
                f"  }}]\n"
                f"}}"
            )
            llm_result = await self._llm_json_chat(user_prompt, temperature=0.5)
            if llm_result and "templates" in llm_result:
                return llm_result

        # 模板兜底
        templates = [
            {
                "target_profile": f"{candidate_name} - {role}@{company}",
                "subject": f"机会分享 - {role} @ [招聘方公司]",
                "template": (
                    f"Hi {candidate_name}，\n\n"
                    f"关注到你在 {company} 担任 {role} 的经历，"
                    f"尤其是在 {personal_note or '行业经验'} 方面的积累。\n\n"
                    f"我们正在为 [招聘方公司] 寻找一位 {role}，"
                    f"这是一个 [关键项目描述] 的机会，\n"
                    f"相信你的背景会非常匹配。\n\n"
                    f"方便约个时间聊聊吗？\n\n"
                    f"Best,\n[您的名字]"
                ),
                "suggested_channel": "linkedin",
                "timing": "工作日 10:00-11:00 发送，回复率较高",
            },
        ]
        return {"candidate": candidate_name, "templates": templates}

    # ── JD 生成（代理至 JDGeneratorService） ──

    async def generate_jd(
        self,
        title: str,
        requirements: str,
        preferences: str = "",
        auto_improve: bool = True,
    ) -> dict:
        """生成职位描述，委托至 JDGeneratorService。"""
        try:
            from app.services.jd_generator import JDGeneratorService
            svc = JDGeneratorService()
            return await svc.generate_jd(
                title=title,
                requirements=requirements,
                preferences=preferences,
                auto_improve=auto_improve,
            )
        except Exception as e:
            logger.warning("JDGen failed, returning stub: %s", e)
            return {
                "title": title,
                "requirements": requirements,
                "fallback": True,
                "message": "JD 生成服务暂不可用，请稍后重试",
            }

    # ── 主入口 ──

    async def run(self, input_data: dict) -> dict:
        agent_type = input_data.get("agent_type", input_data.get("action", "talent_map"))
        # 注意: candidate_search 不再路由到此 agent（orchestrator_graph 已改为 "end"），
        # 由 LLM tool loop 通过 search_platform 工具处理。
        summary_map = {
            "talent_map": "人才 Mapping 完成",
            "channel_strategy": "渠道策略推荐完成",
            "outreach": "触达话术生成完成",
            "jd_generation": "JD 生成完成",
        }

        if agent_type == "talent_map":
            result = await self.build_talent_map(
                target_companies=input_data.get("target_companies", []),
                target_roles=input_data.get("target_roles", []),
            )
        elif agent_type == "channel_strategy":
            result = await self.recommend_channels(
                budget=input_data.get("budget", 10000),
                priority_roles=input_data.get("priority_roles", []),
            )
        elif agent_type == "outreach":
            result = await self.generate_outreach(
                candidate_name=input_data.get("candidate_name", ""),
                company=input_data.get("company", ""),
                role=input_data.get("role", ""),
                personal_note=input_data.get("personal_note", ""),
            )
        elif agent_type == "jd_generation":
            result = await self.generate_jd(
                title=input_data.get("title", ""),
                requirements=input_data.get("requirements", ""),
                preferences=input_data.get("preferences", ""),
                auto_improve=input_data.get("auto_improve", True),
            )
        else:
            result = {"error": f"Unknown action: {agent_type}", "available_actions": ["talent_map", "channel_strategy", "outreach", "jd_generation"]}

        return self.format_result("completed", result, summary_map.get(agent_type, f"寻源 {agent_type} 完成"))
