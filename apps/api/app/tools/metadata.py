"""Tool metadata registry — retry policy, escalation strategy per tool."""

from __future__ import annotations

import enum
import functools
from dataclasses import dataclass, field
from typing import Callable


class EscalationMode(str, enum.Enum):
    NONE = "none"
    REQUIRES_HUMAN = "requires_human"
    REQUIRES_APPROVAL = "requires_approval"


@dataclass
class ToolMetadata:
    retryable: bool = False
    max_retries: int = 0
    escalation: EscalationMode = EscalationMode.NONE
    description: str = ""


TOOL_METADATA: dict[str, ToolMetadata] = {}


def register_tool(
    name: str,
    retryable: bool = False,
    max_retries: int = 0,
    escalation: EscalationMode = EscalationMode.NONE,
    description: str = "",
) -> Callable:
    def decorator(fn: Callable) -> Callable:
        TOOL_METADATA[name] = ToolMetadata(
            retryable=retryable,
            max_retries=max_retries,
            escalation=escalation,
            description=description,
        )
        return fn
    return decorator


def get_metadata(tool_name: str) -> ToolMetadata:
    return TOOL_METADATA.get(tool_name, ToolMetadata())


def is_retryable(tool_name: str) -> bool:
    meta = get_metadata(tool_name)
    return meta.retryable and meta.max_retries > 0


def get_max_retries(tool_name: str) -> int:
    return get_metadata(tool_name).max_retries


def should_escalate(tool_name: str) -> EscalationMode:
    return get_metadata(tool_name).escalation


# ── Tool metadata registration ──────────────────────────────────────────────

# Candidate tools
register_tool(
    "create_candidate",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="创建候选人 — 可能因邮箱重复失败，需要人工确认",
)
register_tool(
    "update_candidate",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="更新候选人 — 瞬态错误可重试",
)
register_tool(
    "archive_candidate",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="归档候选人 — 需要人工确认归档原因",
)

# Candidate search tools
register_tool(
    "search_candidates",
    retryable=True,
    max_retries=2,
    escalation=EscalationMode.NONE,
    description="搜索候选人 — 读操作，瞬态错误可重试",
)
register_tool(
    "get_candidate_detail",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="获取候选人详情 — 读操作，瞬态错误可重试",
)

# Application tools
register_tool(
    "create_application",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="创建申请 — 需要候选人/职位 ID，失败需要人工修复参数",
)
register_tool(
    "update_application_status",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="更新申请状态 — 业务决策类操作，需要人工确认",
)

# Interview tools
register_tool(
    "get_upcoming_interviews",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="查询未来 n 天内的面试日程 — 读操作，瞬态错误可重试",
)
register_tool(
    "get_schedule",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="查询指定月份所有面试日程（含过去和未来）— 读操作，瞬态错误可重试",
)
register_tool(
    "schedule_interview",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="安排面试 — slot 冲突需要人工协调时间",
)
register_tool(
    "cancel_interview",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="取消面试 — 需要人工确认取消原因",
)
register_tool(
    "reschedule_interview",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="改期面试 — 新时间槽冲突需要人工决策",
)
register_tool(
    "complete_interview",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.NONE,
    description="标记面试完成 — 纯状态更新，失败可忽略",
)
register_tool(
    "get_interview_detail",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="获取面试详情 — 读操作，瞬态错误可重试",
)

# Evaluation tools
register_tool(
    "save_evaluation",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="保存评估 — 写入操作，瞬态错误可重试",
)
register_tool(
    "generate_evaluation_report",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="生成评估报告 — 读操作，瞬态错误可重试",
)

# Job tools
register_tool(
    "create_job",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="创建职位 — 失败可能因参数不全，需要人工补充",
)
register_tool(
    "update_job",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="更新职位 — 瞬态错误可重试",
)
register_tool(
    "close_job",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="关闭职位 — 需要人工确认",
)

# Resume / file parsing — always retryable (external service calls)
register_tool(
    "parse_resume",
    retryable=True,
    max_retries=2,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="解析简历 — 外部 OCR/解析服务可能超时",
)
register_tool(
    "parse_file",
    retryable=True,
    max_retries=2,
    escalation=EscalationMode.NONE,
    description="解析文件 — 外部服务，瞬态错误可重试",
)

# Knowledge / screening — retryable read operations
register_tool(
    "search_knowledge",
    retryable=True,
    max_retries=2,
    escalation=EscalationMode.NONE,
    description="知识库搜索 — 向量检索，瞬态错误可重试",
)
register_tool(
    "screen_candidate",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="AI 初筛候选人 — 结果可能需要人工复核",
)

# Dashboard / reporting
register_tool(
    "get_dashboard_stats",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="仪表盘统计 — 读操作，瞬态错误可重试",
)

# JD generation
register_tool(
    "generate_jd",
    retryable=True,
    max_retries=1,
    escalation=EscalationMode.NONE,
    description="生成 JD — LLM 调用，瞬态错误可重试",
)

# Operation log — fire-and-forget, never escalate
register_tool(
    "log_operation",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.NONE,
    description="操作日志 — 非关键操作，失败不影响主流程",
)
