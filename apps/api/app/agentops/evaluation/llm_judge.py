"""LLM Judge 评估引擎 (P2-C Stage 10/12 增强).

为 4 个 LLM judge evaluator 提供真实 LLM 评分能力。
支持可插拔后端：真实 LLM、mock（测试用）、heuristic（回退）。

2026-06-10 新增:
- LLMJudgeFactory: 从 settings 创建 judge 后端的工厂，独立于生产 LLM
- PromptBasedJudge.judge() 降级链: LLM timeout/异常 → HeuristicJudge
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.agentops.evaluation.schemas import EvaluationResult, ScoreType

logger = logging.getLogger(__name__)

type JudgeFn = Callable[[str], Awaitable[str]]
"""Judge 函数签名: 接收完整 prompt → 返回评分理由文本。"""


# ════════════════════════════════════════════════════════════
# Rubric templates
# ════════════════════════════════════════════════════════════

_RESUME_PARSE_RUBRIC = """你是一个简历解析质量评审专家。请评估以下简历解析输出的质量。

【输入】: {input_text}
【解析输出】: {output_text}

评估维度 (每项 0-1):
- completeness: 姓名字段是否存在
- email_present: 邮箱字段是否存在
- skills_present: 技能列表是否非空
- experience_present: 工作年限字段是否存在
- education_present: 教育背景字段是否存在

请返回 JSON: {{"completeness": float, "email_present": float, "skills_present": float, "experience_present": float, "education_present": float, "overall": float, "reasoning": "简短说明"}}
返回纯 JSON，不要其他内容。"""

_SCREENING_RUBRIC = """你是一个候选人筛选评审专家。请评估以下筛选决策的合理性。

【职位要求】: {input_text}
【简历/候选人信息】: {output_text}

评估维度 (每项 0-1):
- requirement_match: 硬性要求匹配程度
- experience_relevance: 经验相关性
- decision_reasonability: 筛选决策的合理性

请返回 JSON: {{"requirement_match": float, "experience_relevance": float, "decision_reasonability": float, "overall": float, "reasoning": "简短说明"}}
返回纯 JSON，不要其他内容。"""

_JD_QUALITY_RUBRIC = """你是一个职位描述(JD)质量评审专家。请评估以下 JD 的质量。

【JD 内容】: {output_text}

评估维度 (每项 0-1):
- clarity: 职责描述是否清晰
- completeness: 是否包含必要的职位要素(职责、要求、福利等)
- fairness: 要求是否合理，无歧视性条款
- attractiveness: 对候选人的吸引力

请返回 JSON: {{"clarity": float, "completeness": float, "fairness": float, "attractiveness": float, "overall": float, "reasoning": "简短说明"}}
返回纯 JSON，不要其他内容。"""

_CONVERSATION_RUBRIC = """你是一个客服对话质量评审专家。请评估以下 AI 回复的质量。

【用户输入】: {input_text}
【AI 回复】: {output_text}

评估维度 (每项 0-1):
- helpfulness: 回复是否对用户有帮助
- relevance: 回复是否相关
- professionalism: 语气是否专业得体
- accuracy: 信息是否准确

请返回 JSON: {{"helpfulness": float, "relevance": float, "professionalism": float, "accuracy": float, "overall": float, "reasoning": "简短说明"}}
返回纯 JSON，不要其他内容。"""


# ════════════════════════════════════════════════════════════
# Score parsing
# ════════════════════════════════════════════════════════════

_RUBRIC_RESPONSE_PATTERN = re.compile(r"\{[\s\S]*\}")


def _parse_score_json(raw: str) -> dict[str, Any] | None:
    """从 LLM 回复中提取 JSON 评分。"""
    m = _RUBRIC_RESPONSE_PATTERN.search(raw)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def _extract_overall(parsed: dict[str, Any]) -> float:
    """从解析结果中提取 overall 分数。"""
    overall = parsed.get("overall")
    if overall is not None:
        return max(0.0, min(1.0, float(overall)))
    # fallback: 各维度平均
    scores = [v for k, v in parsed.items() if k not in ("overall", "reasoning", "reason") and isinstance(v, (int, float))]
    return sum(scores) / len(scores) if scores else 0.5


# ════════════════════════════════════════════════════════════
# LLMJudgeBackend
# ════════════════════════════════════════════════════════════


class LLMJudgeBackend(ABC):
    """LLM Judge 后端抽象 — 可插拔。"""

    @abstractmethod
    async def judge(self, rubric: str, input_text: str, output_text: str) -> tuple[dict[str, Any], str]:
        """执行一次 LLM 评估。

        Args:
            rubric: 评估模板 (含 {input_text} 和 {output_text} 占位符)。
            input_text: 输入文本。
            output_text: 输出文本。

        Returns:
            (parsed_scores, reasoning): parsed_scores 包含各维度分值和 overall。
            reasoning 是 LLM 的评分理由。
        """


class PromptBasedJudge(LLMJudgeBackend):
    """基于 Prompt 的 LLM Judge — 注入 judge_fn 即可使用真实 LLM。

    用法:
        judge = PromptBasedJudge(my_llm_client.chat)
        scores, reasoning = await judge.judge(RUBRIC, input_text, output_text)
    """

    def __init__(self, judge_fn: JudgeFn, *, heuristic_fallback: HeuristicJudge | None = None) -> None:
        self._judge_fn = judge_fn
        self._fallback = heuristic_fallback or HeuristicJudge()

    async def judge(self, rubric: str, input_text: str, output_text: str) -> tuple[dict[str, Any], str]:
        prompt = rubric.format(input_text=input_text or "(无)", output_text=output_text or "(无)")
        try:
            raw = await self._judge_fn(prompt)
        except asyncio.TimeoutError:
            logger.warning("LLM judge timeout, falling back to heuristic")
            return await self._fallback.judge(rubric, input_text, output_text)
        except Exception as exc:
            logger.warning("LLM judge failed (%s), falling back to heuristic", exc)
            return await self._fallback.judge(rubric, input_text, output_text)

        parsed = _parse_score_json(raw)
        if not parsed:
            logger.debug("LLM judge response unparseable: %s", raw[:200])
            return {"overall": 0.5}, f"Unparseable response: {raw[:100]}"

        reasoning = parsed.pop("reasoning", parsed.pop("reason", ""))
        return parsed, reasoning


class HeuristicJudge(LLMJudgeBackend):
    """启发式评估后端 — 不回退到 0.5，而是基于数据质量打分。"""

    async def judge(self, rubric: str, input_text: str, output_text: str) -> tuple[dict[str, Any], str]:
        if not output_text or output_text == "(无)":
            return {"overall": 0.0}, "No output to evaluate"
        length = len(output_text)
        score = min(1.0, length / 500.0) if length > 0 else 0.0
        return {"overall": round(score, 4)}, f"Heuristic: output length {length} chars"


class MockJudge(LLMJudgeBackend):
    """Mock 后端 — 测试用，返回预定分数。"""

    def __init__(self, fixed_overall: float = 0.85) -> None:
        self._fixed_overall = fixed_overall

    async def judge(self, rubric: str, input_text: str, output_text: str) -> tuple[dict[str, Any], str]:
        return {"overall": self._fixed_overall}, "Mock judge"


# ════════════════════════════════════════════════════════════
# LLMJudgeFactory — 从 settings 创建 judge 后端
# ════════════════════════════════════════════════════════════


class LLMJudgeFactory:
    """根据应用配置创建 LLM Judge 后端。

    使用生产 LLM client 基础设施 + model 覆盖（通过 chat() kwargs 传参）。
    构造失败时静默降级到 HeuristicJudge，永不抛异常。

    为什么不用独立 client 实例？
    - OMLXClient/VLLMClient/CN 各 client 的 __init__ 都从 settings 模块级读取，
      不接受构造函数参数。同时修改 5 个 client 的构造函数风险高、影响面大。
    - 折中方案：复用 get_llm_client()，在 chat() 调用时传入 llm_judge_model
      覆盖默认 model。chat() 的 **kwargs 会将 model 传给底层 API。
    - 未来若 LLM client 重构为可接受构造参数，_build_client() 可直接替换。

    用法:
        from app.core.config import settings
        judge = LLMJudgeFactory.from_settings(settings)
        # judge 是 LLMJudgeBackend 实例
    """

    @classmethod
    def from_settings(cls, settings: Any) -> LLMJudgeBackend:
        """根据配置创建 Judge 后端。

        返回 PromptBasedJudge（有 LLM 配置时）或 HeuristicJudge（关闭/失败时）。
        """
        if not getattr(settings, "llm_judge_enabled", False):
            return HeuristicJudge()
        try:
            from app.llm import get_llm_client
            client = get_llm_client()
            fn = cls._make_judge_fn(client, settings)
            return PromptBasedJudge(fn)
        except Exception as exc:
            logger.warning("LLMJudgeFactory init failed (%s), fallback to HeuristicJudge", exc)
            return HeuristicJudge()

    @classmethod
    def _make_judge_fn(cls, client: Any, settings: Any) -> JudgeFn:
        """创建带超时 + model 覆盖的 judge 函数。

        rubric 已包含完整中文评分指令，只需作为 user message 发送。
        通过 chat(**kwargs) 传入 llm_judge_model 覆盖生产 model。
        """
        model = settings.llm_judge_model
        timeout = settings.llm_judge_timeout

        async def fn(prompt: str) -> str:
            return await asyncio.wait_for(
                client.chat([{"role": "user", "content": prompt}], model=model),
                timeout=timeout,
            )
        return fn


# ════════════════════════════════════════════════════════════
# Rubric registry
# ════════════════════════════════════════════════════════════

_RUBRICS: dict[str, str] = {
    ScoreType.RESUME_PARSE_QUALITY: _RESUME_PARSE_RUBRIC,
    ScoreType.SCREENING_REASONABILITY: _SCREENING_RUBRIC,
    ScoreType.JD_QUALITY: _JD_QUALITY_RUBRIC,
    ScoreType.CONVERSATION_HELPFULNESS: _CONVERSATION_RUBRIC,
}


def get_rubric(score_type: str) -> str:
    """获取指定评分类型的 rubric 模板。"""
    return _RUBRICS.get(score_type, "")


def register_rubric(score_type: str, rubric: str) -> None:
    """注册/覆盖 rubric 模板。"""
    _RUBRICS[score_type] = rubric
