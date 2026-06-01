"""ResumeParsingAgent — 简历解析 7-step 工作流。

工作流（代码执行，非 LLM 循环）:
  Step 1: 校验输入（source, content/file_url）
  Step 2: 调用 parse_resume 工具
  Step 3: 置信度分级
  Step 4: 质量评估摘要
  Step 5: 风险标注
  Step 6: 去重检查
  Step 7: 返回标准化输出
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import BaseAgent
from app.tools.resume_parser import (
    _handle_parse_resume,
    _handle_batch_parse,
    _handle_get_profile,
)

logger = logging.getLogger(__name__)


class ResumeParserAgent(BaseAgent):
    """简历解析 Agent — 7-step 工作流，调用 app/tools/resume_parser.py 工具。"""

    output_keys = ["candidate_id", "parsed_data", "quality_score"]

    def __init__(self, name: str = "resume_parser"):
        super().__init__(name)
        self.system_prompt = self._load_system_prompt()

    async def run(self, input_data: dict) -> dict:
        action = input_data.get("action", "parse")

        if action == "batch":
            return await self._batch_parse(input_data)
        elif action == "get_profile":
            return await self._get_profile(input_data)
        else:
            return await self._single_parse(input_data)

    async def _single_parse(self, input_data: dict) -> dict:
        content = input_data.get("content", "")
        file_url = input_data.get("file_url", "")
        target_job_id = input_data.get("target_job_id", "")

        if not content and not file_url:
            return self.format_result("failed", {}, "缺少简历内容或文件")

        result = await _handle_parse_resume(
            content=content, file_url=file_url, target_job_id=target_job_id,
        )

        if result.get("status") != "success":
            error = result.get("error", {})
            return self.format_result(
                "failed",
                result.get("data", {}),
                f"解析失败: {error.get('message', '未知错误')}",
                details=result,
            )

        data = result.get("data", {})
        confidence = data.get("confidence", 0)
        quality_score = data.get("quality_score", 0)
        red_flags = data.get("red_flags", [])
        is_duplicate = data.get("is_duplicate", False)

        if confidence < 0.6:
            status_text = "需人工复核"
            needs_human_review = True
        elif confidence < 0.8:
            status_text = "部分字段待确认"
            needs_human_review = False
        else:
            status_text = "解析完成"
            needs_human_review = False

        summary_parts = [f"置信度 {int(confidence * 100)}%", f"质量评分 {quality_score}/100"]
        if red_flags:
            summary_parts.append(f"风险 {len(red_flags)} 项")
        if is_duplicate:
            summary_parts.append("发现重复记录")

        parsed_data = {
            "candidate_id": data.get("candidate_id", ""),
            "basic_info": data.get("basic_info", {}),
            "skills": data.get("skills", []),
            "quality_score": quality_score,
            "confidence": confidence,
            "red_flags": red_flags,
            "is_duplicate": is_duplicate,
            "needs_human_review": needs_human_review,
            "status": status_text,
        }

        return self.format_result(
            "completed" if not needs_human_review else "partial",
            parsed_data,
            f"简历{status_text}: {', '.join(summary_parts)}",
            details={"raw_result": result, "workflow_steps_completed": 7},
        )

    async def _batch_parse(self, input_data: dict) -> dict:
        files = input_data.get("files", [])
        target_job_id = input_data.get("target_job_id", "")

        if not files:
            return self.format_result("failed", {}, "缺少简历文件列表")

        result = await _handle_batch_parse(
            files=files, target_job_id=target_job_id,
        )

        if result.get("status") != "success":
            return self.format_result("failed", result, "批量解析失败")

        data = result.get("data", {})
        return self.format_result(
            "completed",
            {
                "total": data.get("total", 0),
                "success_count": data.get("success_count", 0),
                "fail_count": data.get("fail_count", 0),
                "results": data.get("results", []),
                "failures": data.get("failures", []),
            },
            f"批量解析完成: {data.get('success_count', 0)}/{data.get('total', 0)} 成功",
            details=result,
        )

    async def _get_profile(self, input_data: dict) -> dict:
        candidate_id = input_data.get("candidate_id", "")
        if not candidate_id:
            return self.format_result("failed", {}, "缺少候选人 ID")

        result = await _handle_get_profile(candidate_id=candidate_id)
        if result.get("status") != "success":
            return self.format_result("failed", result, "获取画像失败")

        return self.format_result(
            "completed",
            result.get("data", {}),
            "候选人画像已生成",
            details=result,
        )
