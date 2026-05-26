"""图3: Router模式 - 多类型任务意图分发。

双策略分类:
1. 关键词规则匹配（降级路径，零依赖）
2. LLM 增强分类（主路径，失败时自动降级）

8 种意图类型:
screening / interview / jd_generation / knowledge_query /
candidate_search / report / settings / chat
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm import get_llm_client

# 意图类型
INTENT_TYPES = [
    "screening",
    "interview",
    "jd_generation",
    "knowledge_query",
    "candidate_search",
    "report",
    "settings",
    "chat",
]

# 关键词规则: (关键词列表, 意图)
_RULES: list[tuple[list[str], str]] = [
    (["筛选", "初筛", "简历筛选", "筛简历", "match resume", "screen"], "screening"),
    (["面试", "安排面试", "预约面试", "schedule interview", "interview"], "interview"),
    (["jd", "职位描述", "生成 jd", "写 jd", "招聘要求", "岗位描述", "generate jd"], "jd_generation"),
    (["知识库", "搜索知识", "查文档", "知识问答", "rag", "knowledge", "文档搜索"], "knowledge_query"),
    (["候选人", "找候选人", "搜索候选人", "candidate", "人才搜索", "找人"], "candidate_search"),
    (["报表", "报告", "数据统计", "统计", "report", "数据看板", "dashboard"], "report"),
    (["设置", "配置", "密码", "个人信息", "settings", "偏好"], "settings"),
    (["聊天", "对话", "你好", "hello", "hi", "help", "帮助"], "chat"),
]

PROMPT_TEMPLATE = """你是一个意图分类器。请判断以下用户输入的意图类型。

可选意图:
- screening: 简历筛选、候选人初筛
- interview: 面试安排、预约
- jd_generation: 生成职位描述
- knowledge_query: 知识库搜索、RAG 查询
- candidate_search: 候选人搜索、人才搜索
- report: 报表、数据统计、dashboard
- settings: 设置、配置、个人信息
- chat: 聊天、对话、帮助

用户输入: 「{text}」

请只返回意图类型名称，不要有其他文字。如果你不确定，返回 "chat"。"""


class RouterAgent(BaseAgent):
    """图3: Router模式 - 多类型任务意图分发"""

    def __init__(self, name: str = "router"):
        super().__init__(name)
        self.routes: dict[str, BaseAgent] = {}
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    def register_route(self, intent: str, agent: BaseAgent) -> None:
        self.routes[intent] = agent

    def _rule_classify(self, text: str) -> tuple[str, float]:
        """关键词规则匹配。返回 (intent, confidence)。"""
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
        """LLM 增强意图分类。失败时降级到规则匹配。"""
        try:
            prompt = PROMPT_TEMPLATE.format(text=text)
            reply = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=20,
            )
            reply = reply.strip().lower()
            for intent in INTENT_TYPES:
                if intent in reply:
                    return intent, 0.97
        except Exception:
            pass

        # 降级到规则匹配
        return self._rule_classify(text)

    async def classify(self, input_data: dict) -> str:
        """分类用户输入，返回意图类型。"""
        text = input_data.get("text", "")
        use_llm = input_data.get("use_llm", True)

        if not text:
            return "chat"

        if use_llm:
            intent, _ = await self._llm_classify(text)
        else:
            intent, _ = self._rule_classify(text)

        return intent

    async def run(self, input_data: dict) -> dict:
        intent = await self.classify(input_data)
        handler = self.routes.get(intent)
        if handler:
            return await handler.run(input_data)
        return {
            "agent": self.name,
            "status": "routed",
            "intent": intent,
            "confidence": 0.95 if intent != "chat" else 0.5,
            "message": f"意图: {intent}",
        }
