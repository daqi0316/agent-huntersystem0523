"""图6: Gen-Eval 循环 Agent — 生成 + 评估迭代，用于 JD 生成等场景。"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agentops.tracing import agent_span
from app.llm import get_llm_client


class GenEvalResult:
    """Gen-Eval 单次迭代结果"""
    iteration: int
    generated: str
    score: float | None
    feedback: str | None
    passed: bool

    def __init__(
        self,
        iteration: int,
        generated: str,
        score: float | None = None,
        feedback: str | None = None,
        passed: bool = False,
    ):
        self.iteration = iteration
        self.generated = generated
        self.score = score
        self.feedback = feedback
        self.passed = passed

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "generated": self.generated,
            "score": self.score,
            "feedback": self.feedback,
            "passed": self.passed,
        }


JD_GENERATE_SYSTEM_PROMPT = """你是一位资深 HR 招聘专家，擅长撰写专业的职位描述（JD）。
请根据用户的输入，生成一份结构清晰、内容完整的职位描述。

JD 必须包含以下结构：
1. **职位标题** — 准确反映职位级别和方向
2. **职位概述** — 2-3 句话说明岗位定位和价值
3. **岗位职责** — 5-8 项具体工作内容（使用项目符号）
4. **任职要求** — 硬性技能要求 + 软性素质要求
5. **加分项** — 额外优势但不必须的条件
6. **薪资范围** — 根据输入信息给出合理范围
7. **团队文化** — 1-2 句话描述团队氛围

使用专业但不冰冷的语言风格。输出格式为 Markdown。"""

JD_EVALUATE_SYSTEM_PROMPT = """你是一位专业的 JD 质量评估师。
请对以下职位描述进行评分，评分维度包括：
1. **完整度** (1-10): 是否包含标题、概述、职责、要求等所有必要部分
2. **清晰度** (1-10): 语言是否清晰易懂，无歧义
3. **专业性** (1-10): 用词是否专业，符合行业标准
4. **吸引力** (1-10): 是否能吸引目标候选人
5. **规范性** (1-10): 格式是否规范，结构是否合理

最后给出总体评分（取各维度平均值），以及改进建议（如完整度 < 7 或总体评分 < 7）。
如果总体评分 >= 7.0，表示 JD 质量达标。

响应格式如下（必须严格遵循）：
总分: <0-10>
改进建议: <具体建议，若无则写"无">

注意：第一行必须是"总分: X.X"，第二行必须是"改进建议: ..."。
不要在上述格式之外输出任何额外内容。"""

JD_IMPROVE_SYSTEM_PROMPT = """你是一位资深 HR 招聘专家，正在根据反馈意见改进一份职位描述。
请保留原始 JD 的良好内容，并根据评估反馈针对性地改进不足。
保持和前一次输出相同的结构（标题、概述、职责、要求、加分项、薪资范围、团队文化），但提升质量。
输出格式为 Markdown。"""


class GenEvalLoop(BaseAgent):
    """图6: Gen-Eval 循环 — 生成 + 评估迭代。

    适用于需要反复生成和改进的场景，如：
    - JD 生成与优化
    - 面试问题生成与评估
    - 评估报告自动生成
    """

    def __init__(self, name: str = "gen_eval", max_iterations: int = 6, threshold: float = 7.0):
        super().__init__(name)
        self.max_iterations = max_iterations
        self.threshold = threshold
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    async def generate(self, input_data: dict, feedback: str | None = None) -> str:
        """生成 JD。如有反馈则根据反馈改进。"""
        title = input_data.get("title", "")
        requirements = input_data.get("requirements", "")
        preferences = input_data.get("preferences", "")

        user_content = f"""请生成一份关于以下职位的 JD：

职位名称: {title}
核心要求: {requirements}
偏好/补充: {preferences}
"""
        if feedback:
            user_content += f"""
---
历史改进意见（请针对以下意见进行修改）:
{feedback}
"""

        messages = [
            {"role": "system", "content": JD_GENERATE_SYSTEM_PROMPT if not feedback else JD_IMPROVE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        result = await self.llm.chat(messages, temperature=0.7, max_tokens=2048)
        return result.strip()

    async def evaluate(self, generated: str) -> tuple[float, str | None]:
        """评估生成的 JD 质量，返回 (总分, 改进建议)。"""
        messages = [
            {"role": "system", "content": JD_EVALUATE_SYSTEM_PROMPT},
            {"role": "user", "content": f"请评估以下职位描述：\n\n{generated}"},
        ]

        result = await self.llm.chat(messages, temperature=0.3, max_tokens=512)
        result = result.strip()

        # Parse score and feedback
        score = 0.0
        feedback: str | None = None

        for line in result.splitlines():
            line = line.strip()
            if line.startswith("总分:"):
                try:
                    score = float(line.replace("总分:", "").strip())
                except ValueError:
                    score = 0.0
            elif line.startswith("改进建议:"):
                val = line.replace("改进建议:", "").strip()
                if val and val != "无":
                    feedback = val

        return score, feedback

    async def run(self, input_data: dict) -> dict:
        """运行 Gen-Eval 循环。"""
        async with agent_span("gen_eval_loop.run", input=input_data, tags=["gen_eval"]):
            iterations: list[GenEvalResult] = []
            final_output: str | None = None
            feedback: str | None = None

            for i in range(1, self.max_iterations + 1):
                async with agent_span(f"gen_eval_loop.iteration_{i}",
                                      input={"iteration": i, "feedback": feedback},
                                      tags=["gen_eval", f"iteration_{i}"]):
                    generated = await self.generate(input_data, feedback=feedback)
                    score, fb = await self.evaluate(generated)

                    passed = score >= self.threshold
                    result = GenEvalResult(
                        iteration=i,
                        generated=generated,
                        score=score,
                        feedback=fb,
                        passed=passed,
                    )
                    iterations.append(result)

                    if passed:
                        final_output = generated
                        break

                    feedback = fb
                    if i == self.max_iterations:
                        final_output = generated

            return {
            "agent": self.name,
            "status": "completed",
            "final_output": final_output or iterations[-1].generated,
            "iterations": [r.to_dict() for r in iterations],
            "total_iterations": len(iterations),
            "passed": any(r.passed for r in iterations),
            "threshold": self.threshold,
        }
