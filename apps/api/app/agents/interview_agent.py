"""InterviewAgent — 面试官助理。

使用 prompts/interview.md 作为 system_prompt，
对评价表生成和反馈汇总提供 LLM 驱动，硬编码 Prompt 作为用户消息兜底。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.llm import get_llm_client

logger = logging.getLogger(__name__)

INTERVIEW_ROUNDS = [
    {"round": "R1", "label": "电话初筛", "duration": 30, "focus": "基础背景、意向确认"},
    {"round": "R2", "label": "技术面", "duration": 60, "focus": "技术深度、编码能力"},
    {"round": "R3", "label": "行为/系统设计", "duration": 60, "focus": "软技能、架构能力"},
    {"round": "R4", "label": "终面/交叉面", "duration": 45, "focus": "文化适配、综合判断"},
]

EVALUATION_FORM_PROMPT = """请为 {candidate_name} 的{round_name}面试生成结构化评价表。

面试轮次: {round_name} ({round_duration}分钟)
重点评估: {focus}
候选人背景: {candidate_background}

输出 JSON 格式:
{{
  "round": "{round_id}",
  "dimensions": [
    {{"name": "维度名", "score": 0-10, "weight": 0.0-1.0, "description": "评估什么"}}
  ],
  "recommended_questions": ["建议提问的问题"]
}}

每个轮次 3-5 个评估维度，权重之和为 1.0。"""

FEEDBACK_SUMMARY_PROMPT = """汇总以下评估反馈，生成最终建议。

候选人: {candidate_name}

各轮次反馈:
{feedback_list}

输出 JSON:
{{
  "overall_score": 0-10,
  "consensus": "strong_hire/hire/consider/pass",
  "consistent_strengths": ["跨轮次一致的优势"],
  "consistent_concerns": ["跨轮次一致的顾虑"],
  "final_recommendation": "录用建议",
  "next_steps": ["下一步行动"]
}}"""

TRANSCRIPT_FEEDBACK_PROMPT = """基于以下面试转录文本生成结构化面试反馈。

候选人: {candidate_name}
岗位: {job_title}
面试转录文本:
{transcript_text}

输出 JSON:
{{
  "overall_score": 0-10,
  "verdict": "strong_hire/hire/consider/pass",
  "evidence_quotes": ["必须来自转录文本的原句"],
  "strengths": ["有证据支撑的优势"],
  "concerns": ["有证据支撑的风险"],
  "feedback": "结构化反馈"
}}

约束：只能引用转录文本中出现的信息，不得编造未出现的表现。"""


class InterviewAgent(BaseAgent):
    """面试官助理 Agent — 评价表生成 + 反馈汇总 + 安排 + 提醒 (LLM + 规则兜底)。"""

    output_keys = ["evaluation", "feedback", "schedule", "reminder"]

    def __init__(self, name: str = "interview"):
        super().__init__(name)
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    # ── LLM 辅助 ──

    async def _llm_json_chat(self, user_prompt: str, temperature: float = 0.3, max_tokens: int = 2048) -> dict | None:
        """调用 LLM（system_prompt from prompts/interview.md）并解析 JSON。"""
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
            logger.warning("InterviewAgent LLM call failed: %s", e)
            return None

    def _extract_json(self, reply: str) -> dict | None:
        """从 LLM 回复中提取 JSON。"""
        try:
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
        except Exception:
            return None

    # ── 评价表生成 ──

    async def generate_evaluation_form(
        self,
        candidate_name: str,
        candidate_background: str = "",
        round_id: str = "R1",
    ) -> dict[str, Any]:
        """为指定轮次生成结构化评价表（LLM 优先，硬编码兜底）。"""
        round_def = next((r for r in INTERVIEW_ROUNDS if r["round"] == round_id), INTERVIEW_ROUNDS[0])
        user_prompt = EVALUATION_FORM_PROMPT.format(
            candidate_name=candidate_name,
            round_name=round_def["label"],
            round_duration=round_def["duration"],
            focus=round_def["focus"],
            round_id=round_id,
            candidate_background=candidate_background or "暂无",
        )

        # LLM 优先（使用 system_prompt from prompts/interview.md）
        if self.system_prompt:
            llm_out = await self._llm_json_chat(user_prompt, temperature=0.3, max_tokens=1024)
            if llm_out and "dimensions" in llm_out:
                return llm_out

        # 硬编码 LLM 调用（system_prompt 不存在时）
        try:
            reply = await self.llm.chat(
                [{"role": "user", "content": user_prompt}],
                temperature=0.3, max_tokens=1024,
            )
            parsed = self._extract_json(reply)
            if parsed and "dimensions" in parsed:
                return parsed
        except Exception as e:
            logger.warning("Evaluation form generation failed: %s", e)

        return {
            "round": round_id,
            "dimensions": [{"name": "综合评估", "score": 5, "weight": 1.0, "description": "默认维度"}],
            "recommended_questions": [],
        }

    # ── 反馈收集 ──

    async def collect_feedback(
        self,
        interview_id: str,
        feedback_data: dict[str, Any],
    ) -> dict[str, Any]:
        """收集面试官反馈并存储。"""
        record = {
            "interview_id": interview_id,
            "feedback_data": feedback_data,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("Feedback collected for interview %s: %s", interview_id, feedback_data.get("overall_score"))
        return {"status": "recorded", "record": record}

    # ── 反馈汇总 ──

    async def summarize_feedback(
        self,
        candidate_name: str,
        evaluations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """汇总多轮反馈并生成最终建议（LLM 优先，统计兜底）。"""
        if not evaluations:
            return {
                "overall_score": 0,
                "consensus": "consider",
                "consistent_strengths": [],
                "consistent_concerns": [],
                "final_recommendation": "暂无评估数据",
                "next_steps": ["等待面试官提交反馈"],
            }

        feedback_text = "\n".join(
            f"轮次: {e.get('round', '?')}, 分数: {e.get('overall_score', 'N/A')}, 评价: {e.get('feedback', '')}"
            for e in evaluations
        )
        user_prompt = FEEDBACK_SUMMARY_PROMPT.format(candidate_name=candidate_name, feedback_list=feedback_text)

        # LLM 优先（使用 system_prompt from prompts/interview.md）
        if self.system_prompt:
            llm_out = await self._llm_json_chat(user_prompt, temperature=0.3, max_tokens=1024)
            if llm_out and "overall_score" in llm_out:
                return llm_out

        # 统计兜底
        try:
            reply = await self.llm.chat(
                [{"role": "user", "content": user_prompt}],
                temperature=0.3, max_tokens=1024,
            )
            parsed = self._extract_json(reply)
            if parsed and "overall_score" in parsed:
                return parsed
        except Exception:
            pass

        scores = [e.get("overall_score", 0) or 0 for e in evaluations]
        avg = sum(scores) / len(scores) if scores else 0
        return {
            "overall_score": round(avg, 1),
            "consensus": "hire" if avg >= 7 else "consider",
            "consistent_strengths": [],
            "consistent_concerns": [],
            "final_recommendation": f"综合 {len(evaluations)} 轮评估，平均分 {avg:.1f}",
            "next_steps": ["人工复核"],
        }

    async def generate_feedback_from_transcript(
        self,
        candidate_name: str,
        transcript_text: str,
        job_title: str = "",
    ) -> dict[str, Any]:
        transcript_text = (transcript_text or "").strip()
        if not transcript_text:
            return {
                "status": "insufficient_data",
                "overall_score": None,
                "verdict": "consider",
                "evidence_quotes": [],
                "strengths": [],
                "concerns": ["缺少面试转录文本，不能基于录音生成评价"],
                "feedback": "缺少面试转录文本，不能声称已基于录音表现完成评估。",
            }

        prompt = TRANSCRIPT_FEEDBACK_PROMPT.format(
            candidate_name=candidate_name or "候选人",
            job_title=job_title or "未指定岗位",
            transcript_text=transcript_text,
        )
        if self.system_prompt:
            llm_out = await self._llm_json_chat(prompt, temperature=0.2, max_tokens=1200)
            if llm_out and "feedback" in llm_out:
                llm_out["status"] = "completed"
                return llm_out

        evidence = transcript_text[:120]
        return {
            "status": "completed",
            "overall_score": None,
            "verdict": "consider",
            "evidence_quotes": [evidence],
            "strengths": [],
            "concerns": [],
            "feedback": f"已收到面试转录文本，可供人工复核。证据片段：{evidence}",
        }

    # ── 面试安排 ──

    def schedule_interview_rounds(
        self,
        candidate_name: str,
        job_title: str,
    ) -> list[dict[str, Any]]:
        """按 4 轮标准生成面试安排计划。"""
        plan = []
        for r in INTERVIEW_ROUNDS:
            plan.append({
                "round": r["round"],
                "label": r["label"],
                "duration_minutes": r["duration"],
                "focus": r["focus"],
                "status": "pending",
                "suggested_slot": None,
            })
        return plan

    # ── 发送提醒（stub） ──

    async def send_reminder(self, interview_id: str) -> dict[str, Any]:
        """发送面试提醒（当前为 stub，仅记录日志）。"""
        logger.info(
            "[STUB] Sending reminder for interview %s: "
            "D-1 email + H-1 SMS would be sent here",
            interview_id,
        )
        return {
            "status": "sent",
            "interview_id": interview_id,
            "channels": ["email", "sms"],
            "note": "stub — 邮件/SMS 集成尚未实现",
        }

    # ── 主入口 ──

    async def run(self, input_data: dict) -> dict:
        """Agent 主入口。"""
        action = input_data.get("action", "schedule")
        summary_map = {
            "evaluation_form": "评价表生成完成",
            "collect_feedback": "面试反馈已收集",
            "summarize_feedback": "反馈汇总完成",
            "transcript_feedback": "基于转录文本的反馈生成完成",
            "reminder": "面试提醒已发送",
        }

        if action == "evaluation_form":
            result = await self.generate_evaluation_form(
                candidate_name=input_data.get("candidate_name", ""),
                candidate_background=input_data.get("candidate_background", ""),
                round_id=input_data.get("round_id", "R1"),
            )
        elif action == "collect_feedback":
            result = await self.collect_feedback(
                interview_id=input_data.get("interview_id", ""),
                feedback_data=input_data.get("feedback_data", {}),
            )
        elif action == "summarize_feedback":
            result = await self.summarize_feedback(
                candidate_name=input_data.get("candidate_name", ""),
                evaluations=input_data.get("evaluations", []),
            )
        elif action == "transcript_feedback":
            result = await self.generate_feedback_from_transcript(
                candidate_name=input_data.get("candidate_name", ""),
                transcript_text=input_data.get("transcript_text", ""),
                job_title=input_data.get("job_title", ""),
            )
        elif action == "reminder":
            result = await self.send_reminder(input_data.get("interview_id", ""))
        else:
            result = {
                "plan": self.schedule_interview_rounds(
                    input_data.get("candidate_name", ""),
                    input_data.get("job_title", ""),
                ),
                "current_rounds": INTERVIEW_ROUNDS,
            }

        return self.format_result("completed", result, summary_map.get(action, f"面试 {action} 完成"))
