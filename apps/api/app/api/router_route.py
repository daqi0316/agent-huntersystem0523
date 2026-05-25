"""图3: 全局意图路由 — 用户输入 → 意图分类。

双策略实现:
1. 规则匹配（关键词）— 快速、零依赖
2. LLM 增强（可选）— 更准确、处理歧义

输出意图类型: screening / interview / jd_generation / knowledge_query /
candidate_search / report / settings / chat
"""

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.llm import get_llm_client

router = APIRouter()

# --- 意图类型 ---
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


class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="用户输入文本")
    session_id: str | None = Field(None, max_length=256, description="会话 ID（可选，用于上下文）")
    use_llm: bool = Field(True, description="是否尝试 LLM 增强（失败时降级规则）")


class ClassifyResponse(BaseModel):
    success: bool = True
    intent: str = "chat"
    confidence: float = 0.0
    method: str = "rule"  # "rule" or "llm"
    detail: str = ""


# --- 规则引擎 ---

# 每条规则: (关键词列表, 意图)
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


def _rule_classify(text: str) -> tuple[str, float]:
    """关键词规则匹配。返回 (intent, confidence)。"""
    text_lower = text.lower()

    best_intent = "chat"
    best_score = 0.0

    for keywords, intent in _RULES:
        score = 0.0
        for kw in keywords:
            if kw.lower() in text_lower:
                # 更长的关键词给更高权重
                score += len(kw) / 10.0

        if score > best_score:
            best_score = score
            best_intent = intent

    # 置信度 = 归一化后的分数（上限 0.95，纯规则不可能 1.0）
    confidence = min(best_score, 0.95)
    return best_intent, confidence


def _build_llm_prompt(text: str) -> str:
    intent_list = "\n".join(f"- {t}" for t in INTENT_TYPES)
    return f"""你是一个意图分类器。请判断以下用户输入的意图类型。

可选意图:
{intent_list}

用户输入: 「{text}」

请只返回意图类型名称，不要有其他文字。如果你不确定，返回 "chat"。"""


async def _llm_classify(text: str) -> tuple[str, float, str]:
    """使用 LLM 进行意图分类。返回 (intent, confidence, method)。"""
    try:
        llm = get_llm_client()
        prompt = _build_llm_prompt(text)
        reply = await llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=20,
        )
        reply = reply.strip().lower()

        # 验证返回的意图是否合法
        for intent in INTENT_TYPES:
            if intent in reply:
                return intent, 0.97, "llm"

        # LLM 返回了非法意图，降级到规则
        intent, conf = _rule_classify(text)
        return intent, conf, "rule"

    except Exception:
        # LLM 不可用，降级到规则
        intent, conf = _rule_classify(text)
        return intent, conf, "rule"


@router.post("/classify", response_model=ClassifyResponse)
async def classify_intent(req: ClassifyRequest):
    """图3: 全局意图识别 — 将用户输入分类到对应 Agent 类型。

    优先尝试 LLM 分类（若 use_llm=True），失败或不可用时
    自动降级到关键词规则匹配。
    """
    if req.use_llm:
        intent, confidence, method = await _llm_classify(req.text)
    else:
        intent, confidence = _rule_classify(req.text)
        method = "rule"

    return ClassifyResponse(
        success=True,
        intent=intent,
        confidence=round(confidence, 4),
        method=method,
        detail=f"意图: {intent} (置信度: {confidence:.2f}, 方法: {method})",
    )
