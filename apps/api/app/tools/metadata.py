"""Tool metadata registry — retry policy, escalation, capability, Pydantic input per tool.

向后兼容：旧 register_tool() 调用照常工作。
新功能（v4 V-3 Pydantic 强校验）：
  - register_tool() 加 input_model / capability / requires_role / version / rate_limit
  - get_input_model() 查 Pydantic BaseModel
  - get_capability() 查 read/write/destructive/admin
"""
from __future__ import annotations

import enum
import functools
from dataclasses import dataclass, field
from typing import Callable, Optional, Type

try:
    from pydantic import BaseModel
    PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    PYDANTIC_AVAILABLE = False
    BaseModel = None  # type: ignore


class EscalationMode(str, enum.Enum):
    NONE = "none"
    REQUIRES_HUMAN = "requires_human"
    REQUIRES_APPROVAL = "requires_approval"


class Capability(str, enum.Enum):
    """工具能力分级（V-3 RBAC 依据）。"""

    READ = "read"               # 读操作（get_*, list_*, search_*）
    WRITE = "write"             # 写操作（create_*, update_*）
    DESTRUCTIVE = "destructive" # 破坏性（delete_*, archive_*, cancel_*）
    ADMIN = "admin"             # 管理（install_skill, drop_cache）


@dataclass
class ToolMetadata:
    retryable: bool = False
    max_retries: int = 0
    escalation: EscalationMode = EscalationMode.NONE
    description: str = ""
    # ── v4 新增字段（V-3/V-4 修复）──
    input_model: Optional[Type] = None  # Pydantic BaseModel，call_tool 前强校验
    capability: Capability = Capability.READ
    requires_role: Optional[str] = None  # hr / admin / recruiter
    rate_limit: int = 0  # 每用户每小时最多 N 次（0 = 不限）
    version: str = "1.0.0"
    deprecated: bool = False
    replacement: Optional[str] = None


TOOL_METADATA: dict[str, ToolMetadata] = {}


def register_tool(
    name: str,
    *,
    retryable: bool = False,
    max_retries: int = 0,
    escalation: EscalationMode = EscalationMode.NONE,
    description: str = "",
    # v4 新增（全部可选，向后兼容）
    input_model: Optional[Type] = None,
    capability: Capability | str = Capability.READ,
    requires_role: Optional[str] = None,
    rate_limit: int = 0,
    version: str = "1.0.0",
    deprecated: bool = False,
    replacement: Optional[str] = None,
    # ── 双用法支持：handler 显式传入时立即注册（v4 V-3 修复）──
    handler: Optional[Callable] = None,
) -> Callable:
    """注册 tool metadata。两种用法：

    1. 装饰器（向后兼容）：
        @register_tool("calc", retryable=True, input_model=CalculateInput)
        def calc_handler(...): ...

    2. 直接调用（用于已存在的 _handle_xxx 函数，v4 修复 register_tool 当函数调用的 bug）：
        register_tool("calc", handler=_handle_calc, input_model=CalculateInput, retryable=True)
    """
    # 接受 str 或 enum
    if isinstance(capability, str):
        try:
            cap = Capability(capability)
        except ValueError:
            cap = Capability.READ
    else:
        cap = capability

    def _build_entry(fn: Optional[Callable] = None) -> None:
        TOOL_METADATA[name] = ToolMetadata(
            retryable=retryable,
            max_retries=max_retries,
            escalation=escalation,
            description=description,
            input_model=input_model,
            capability=cap,
            requires_role=requires_role,
            rate_limit=rate_limit,
            version=version,
            deprecated=deprecated,
            replacement=replacement,
        )

    if handler is not None:
        # 用法 2：直接调用，立即注册
        _build_entry()
        return handler

    # 用法 1：装饰器
    def decorator(fn: Callable) -> Callable:
        _build_entry()
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


# ── v4 新增查询 API ──────────────────────────────────────────────────────
def get_input_model(tool_name: str) -> Optional[Type]:
    return get_metadata(tool_name).input_model


def get_capability(tool_name: str) -> Capability:
    return get_metadata(tool_name).capability


def get_requires_role(tool_name: str) -> Optional[str]:
    return get_metadata(tool_name).requires_role


def is_deprecated(tool_name: str) -> bool:
    return get_metadata(tool_name).deprecated


def deprecate_tool(name: str, replacement: Optional[str] = None) -> None:
    """标 deprecated（V-4 schema 演进）。"""
    if name in TOOL_METADATA:
        TOOL_METADATA[name].deprecated = True
        TOOL_METADATA[name].replacement = replacement


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
    "retry_raw_resume",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.NONE,
    description="重试解析失败的简历 — 用户主动触发，不归 supervisor 自动 retry",
)
register_tool(
    "parse_resume_async",
    retryable=True,
    max_retries=2,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="异步解析简历 — enqueue RQ task, 不阻塞等待 LLM",
)
register_tool(
    "poll_parse_resume",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.NONE,
    description="轮询异步解析任务状态 — 用户主动调用",
)
# v0.7: skill_mgr 4 新工具
register_tool(
    "list_skills",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.NONE,
    description="列出已装 skill — 读操作无需 admin",
)
register_tool(
    "get_skill_info",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.NONE,
    description="查 skill 详情 — 读操作无需 admin",
)
register_tool(
    "enable_skill",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="启用 skill — admin only (requires_role=admin)",
)
register_tool(
    "disable_skill",
    retryable=False,
    max_retries=0,
    escalation=EscalationMode.REQUIRES_HUMAN,
    description="禁用 skill — admin only (requires_role=admin)",
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
