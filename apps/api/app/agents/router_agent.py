"""RouterAgent — 意图分类与路由层。

双策略分类：
1. LLM 优先（使用 prompts/router.md 作为 system_prompt）
2. 关键词规则匹配（降级路径，零依赖）

路由到 Specialist Agent (ScreeningAgent/SourcingAgent/InterviewAgent/OfferingAgent/OnboardingAgent/AnalyticsAgent)
"""

from __future__ import annotations

import json
import logging

from app.agents.base import BaseAgent
from app.llm import get_llm_client

logger = logging.getLogger(__name__)

INTENT_TYPES = [
    "resume_parser",
    "screening",
    "interview",
    "jd_generation",
    "knowledge_query",
    "candidate_search",
    "report",
    "settings",
    "chat",
    "offering",
    "onboarding",
    "analytics",
]

_RULES: list[tuple[list[str], str]] = [
    (["解析简历", "解析", "简历解析", "parse resume", "提取简历", "简历提取", "parse_resume"], "resume_parser"),
    (["筛选", "初筛", "简历筛选", "筛简历", "match resume", "screen"], "screening"),
    (["面试", "安排面试", "预约面试", "schedule interview", "interview"], "interview"),
    (["jd", "职位描述", "生成 jd", "写 jd", "招聘要求", "岗位描述", "generate jd"], "jd_generation"),
    (["知识库", "搜索知识", "查文档", "知识问答", "rag", "knowledge", "文档搜索"], "knowledge_query"),
    (["候选人", "找候选人", "搜索候选人", "candidate", "人才搜索", "找人"], "candidate_search"),
    (["报表", "报告", "数据统计", "统计", "report", "数据看板", "dashboard"], "report"),
    (["设置", "配置", "密码", "个人信息", "settings", "偏好"], "settings"),
    (["聊天", "对话", "你好", "hello", "hi", "help", "帮助", "现在几点", "几点", "时间", "日期", "天气", "日程", "明天", "后天", "预报", "未来", "明天天气", "后天天气"], "chat"),
    (["offer", "录用", "发 offer", "薪酬", "谈薪", "薪资", "offering"], "offering"),
    (["入职", "onboarding", "迎新", "入职流程", "转正", "培训", "上岗"], "onboarding"),
    (["数据", "统计", "kpi", "漏斗", "渠道", "analytics", "仪表盘"], "analytics"),
]

_MULTI_INTENT_KEYWORDS = ["然后", "并且", "同时", "之后", "接着", "先", "再", "首先", "最后", "and", "then", "also"]


class RouterAgent(BaseAgent):
    """RouterAgent — 意图分类与路由（LLM 优先，规则兜底）。"""

    def __init__(self, name: str = "router"):
        super().__init__(name)
        self.routes: dict[str, BaseAgent] = {}
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    def is_multi_intent(self, text: str) -> bool:
        text_lower = text.lower()
        for kw in _MULTI_INTENT_KEYWORDS:
            if kw in text_lower:
                return True
        hit = 0
        for keywords, _intent in _RULES:
            for kw in keywords:
                if kw.lower() in text_lower:
                    hit += 1
                    if hit >= 2:
                        return True
                    break
        return False

    def register_route(self, intent: str, agent: BaseAgent) -> None:
        self.routes[intent] = agent
        try:
            from app.agents.registry import AgentRegistry
            AgentRegistry.register(f"router_{intent}", agent)
        except ImportError:
            pass

    def get_available_intents(self) -> list[str]:
        local = set(self.routes.keys())
        try:
            from app.agents.registry import AgentRegistry
            for name in AgentRegistry.list_agents():
                if name.startswith("router_"):
                    local.add(name[7:])
        except ImportError:
            pass
        return list(local | set(INTENT_TYPES))

    async def _llm_json_chat(self, user_prompt: str, temperature: float = 0.1, max_tokens: int = 50) -> dict | None:
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
            logger.warning("RouterAgent LLM call failed: %s", e)
            return None

    def _rule_classify(self, text: str) -> tuple[str, float]:
        text_lower = text.lower()
        best_intent = "chat"
        best_score = 0.0
        for keywords, intent in _RULES:
            score = 0.0
            for kw in keywords:
                if kw.lower() in text_lower:
                    score += len(kw) / 10.0
            if score > best_score:
                best_score = score
                best_intent = intent
        confidence = min(best_score, 0.95)
        return best_intent, confidence

    async def _llm_classify(self, text: str) -> tuple[str, float]:
        if self.system_prompt:
            try:
                user_prompt = (
                    f"请判断以下用户输入的意图类型。\n\n"
                    f"用户输入: 「{text}」\n\n"
                    f"输出 JSON：{{\"intent\": \"screening|interview|jd_generation|knowledge_query|candidate_search|report|settings|chat|offering|onboarding|analytics\"}}"
                )
                llm_out = await self._llm_json_chat(user_prompt)
                if llm_out and "intent" in llm_out:
                    intent = llm_out["intent"].strip().lower()
                    if intent in INTENT_TYPES:
                        return intent, 0.97
            except Exception:
                pass
        return self._rule_classify(text)

    async def classify(self, input_data: dict) -> str:
        text = input_data.get("text", "")
        use_llm = input_data.get("use_llm", True)

        if not text:
            return "chat"

        if self.is_multi_intent(text):
            return "orchestrator"

        if use_llm:
            intent, _ = await self._llm_classify(text)
        else:
            intent, _ = self._rule_classify(text)

        rule_intent, rule_score = self._rule_classify(text)
        if rule_intent == "chat" and rule_score > 0.3 and intent != "chat":
            logger.info("Router: rule override LLM (%s -> chat) for input: %s", intent, text[:50])
            intent = "chat"

        return intent

    async def run(self, input_data: dict) -> dict:
        intent = await self.classify(input_data)

        handler = self.routes.get(intent)
        if handler is None:
            try:
                from app.agents.registry import AgentRegistry
                handler = AgentRegistry.resolve(f"router_{intent}")
            except ImportError:
                pass

        if handler:
            text = input_data.get("text", "")
            try:
                from app.agents.param_extractor import extract_params
                params = extract_params(text, intent)
                enriched = {**input_data, **params}
            except Exception:
                logger.warning("Param extraction failed, using raw input", exc_info=True)
                enriched = input_data
            return await handler.run(enriched)
        return {
            "agent": self.name,
            "status": "routed",
            "intent": intent,
            "confidence": 0.95 if intent != "chat" else 0.5,
            "message": f"意图: {intent}",
        }
