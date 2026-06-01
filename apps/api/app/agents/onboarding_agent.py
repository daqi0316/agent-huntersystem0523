"""OnboardingAgent — 迎新官。

使用 prompts/onboarding.md 作为 system_prompt，
对入职计划和转正评估提供 LLM 驱动，规则逻辑兜底。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.base import BaseAgent
from app.llm import get_llm_client

logger = logging.getLogger(__name__)

ONBOARDING_MILESTONES = [
    {"id": "M1", "name": "入职通知发送", "due": "D-7", "owner": "HR", "description": "发送入职邮件、IT 账号准备"},
    {"id": "M2", "name": "入职确认", "due": "D-1", "owner": "HR", "description": "确认入职安排、发送指引"},
    {"id": "M3", "name": "入职日引导", "due": "D1", "owner": "HR+上级", "description": "入职日引导、团队介绍"},
    {"id": "M4", "name": "环境搭建完成", "due": "W1", "owner": "IT+上级", "description": "开发环境搭建、初期任务分配"},
    {"id": "M5", "name": "首次Check-in", "due": "W2", "owner": "上级", "description": "首次 1-on-1 会议"},
    {"id": "M6", "name": "一个月回顾", "due": "M1", "owner": "上级", "description": "入职一个月回顾交流"},
    {"id": "M7", "name": "中期评估", "due": "M2", "owner": "HR+上级", "description": "试用期中期评估"},
    {"id": "M8", "name": "转正评估", "due": "M3", "owner": "HR+上级", "description": "转正评审"},
]


class OnboardingAgent(BaseAgent):
    """入职管理 Agent — 计划、跟踪、评估 (LLM + 规则兜底)。"""

    output_keys = ["plan", "tasks", "progress", "feedback", "evaluation"]

    def __init__(self, name: str = "onboarding"):
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
            logger.warning("OnboardingAgent LLM call failed: %s", e)
            return None

    # ── 入职计划（LLM 优先） ──

    async def generate_plan(self, candidate_name: str, title: str, department: str) -> dict:
        """生成个性化入职计划（LLM 优先，模板兜底）。"""
        if self.system_prompt:
            user_prompt = (
                f"请为以下新员工生成个性化入职计划。\n\n"
                f"姓名：{candidate_name}\n职位：{title}\n部门：{department}\n\n"
                f"输出 JSON：{{\n"
                f'  "candidate_name": "...",\n'
                f'  "title": "...",\n'
                f'  "department": "...",\n'
                f'  "onboarding_plan": {{\n'
                f'    "milestones": [{{\n'
                f'      "id": "M1", "name": "...", "due": "D-7",\n'
                f'      "owner": "HR", "description": "...", "status": "pending"\n'
                f"    }}]\n"
                f'  }},\n'
                f'  "check_in_schedule": [{{\n'
                f'    "week": 1, "type": "1-on-1", "participants": [], "topics": []\n'
                f"  }}]\n"
                f"}}"
            )
            llm_out = await self._llm_json_chat(user_prompt)
            if llm_out and "onboarding_plan" in llm_out:
                return llm_out

        # 模板兜底
        milestones = [
            {"id": m["id"], "name": m["name"], "due": m["due"], "owner": m["owner"], "description": m["description"], "status": "pending"}
            for m in ONBOARDING_MILESTONES
        ]
        check_in_schedule = [
            {"week": 1, "type": "1-on-1", "participants": ["直属上级"], "topics": ["入职体验", "环境熟悉度"]},
            {"week": 2, "type": "1-on-1", "participants": ["直属上级"], "topics": ["任务进展", "团队融入"]},
            {"week": 4, "type": "monthly_review", "participants": ["直属上级", "HR"], "topics": ["月度回顾", "目标对齐"]},
            {"week": 8, "type": "mid_review", "participants": ["直属上级", "HR"], "topics": ["中期评估", "改进方向"]},
            {"week": 12, "type": "probation_review", "participants": ["直属上级", "HR", "部门负责人"], "topics": ["转正评估"]},
        ]
        return {"candidate_name": candidate_name, "title": title, "department": department, "onboarding_plan": {"milestones": milestones}, "check_in_schedule": check_in_schedule}

    # ── 里程碑更新（规则驱动） ──

    def update_milestone(self, plan: dict, milestone_id: str, status: str, note: str = "") -> dict:
        milestones = plan.get("onboarding_plan", {}).get("milestones", [])
        updated = False
        for m in milestones:
            if m["id"] == milestone_id:
                m["status"] = status
                if note:
                    m["note"] = note
                updated = True
                break
        return {**plan, "updated": updated, "milestone_id": milestone_id, "new_status": status}

    # ── 转正评估（LLM 优先） ──

    async def probation_review(self, candidate_name: str, score: float = 7.0, feedback: str = "", recommendation: str = "按期转正") -> dict:
        """生成转正评估（LLM 优先，规则兜底）。"""
        if self.system_prompt:
            user_prompt = (
                f"请为以下员工生成转正评估。\n\n"
                f"姓名：{candidate_name}\n评分：{score}\n反馈：{feedback or '暂无'}\n建议：{recommendation}\n\n"
                f"输出 JSON：{{\n"
                f'  "candidate_name": "...",\n'
                f'  "probation_review": {{\n'
                f'    "status": "on_track|at_risk|concerned",\n'
                f'    "score": {score},\n'
                f'    "feedback": "...",\n'
                f'    "recommendation": "按期转正|延长试用|不予转正"\n'
                f"  }}\n"
                f"}}"
            )
            llm_out = await self._llm_json_chat(user_prompt)
            if llm_out and "probation_review" in llm_out:
                return llm_out

        # 规则兜底
        status = "on_track"
        if score < 5:
            status = "concerned"
        elif score < 7:
            status = "at_risk"
        return {"candidate_name": candidate_name, "probation_review": {"status": status, "score": score, "feedback": feedback or "暂无详细反馈", "recommendation": recommendation}}

    # ── 主入口 ──

    async def run(self, input_data: dict) -> dict:
        action = input_data.get("action", "plan")
        summary_map = {"plan": "入职计划生成完成", "update_milestone": "里程碑状态已更新", "probation_review": "转正评估完成"}

        if action == "plan":
            result = await self.generate_plan(candidate_name=input_data.get("candidate_name", ""), title=input_data.get("title", ""), department=input_data.get("department", ""))
        elif action == "update_milestone":
            result = self.update_milestone(plan=input_data.get("plan", {}), milestone_id=input_data.get("milestone_id", ""), status=input_data.get("status", "pending"), note=input_data.get("note", ""))
        elif action == "probation_review":
            result = await self.probation_review(candidate_name=input_data.get("candidate_name", ""), score=input_data.get("score", 7.0), feedback=input_data.get("feedback", ""), recommendation=input_data.get("recommendation", "按期转正"))
        else:
            result = {"error": f"Unknown action: {action}", "available_actions": ["plan", "update_milestone", "probation_review"]}

        return self.format_result("completed", result, summary_map.get(action, f"入职 {action} 完成"))
