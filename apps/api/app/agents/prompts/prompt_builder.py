"""分层 Prompt 组装器 — Hermes-style 6 层架构。

提供:
- PromptBundle: 9 字段 dataclass（SOUL/MEMORY/USER/PROJECT/SKILLS/AGENT/SAFETY/ENV/EPHEMERAL）
- build_layered_prompt: 组装完整 PromptBundle
- assemble: 把 PromptBundle 拼成最终 system prompt 字符串
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PromptBundle:
    """9 层 Prompt 容器 — 每层独立字段，便于单独缓存 + 单独失效。"""

    soul: str  # Layer 1: 稳定（admin hardcode）
    memory: str  # Layer 2: 组织（admin hardcode）
    user: str  # Layer 3: 用户（per user，文件系统）
    project: str  # Layer 4: 项目（AGENTS.md 预留，v1 留空）
    skills_index: str  # Layer 5: 技能索引（v1 留空，工具化后不注入）
    agent: str  # Layer 6: Agent 专层（screening.md / interview.md / ...）
    safety: str  # Layer 7: 安全（每次强制注入）
    env: str  # Layer 8: 环境（时间/租户/语言）
    ephemeral: str = ""  # Layer 9: 临时（不缓存，最高优先级）


# Lazy import from __init__.py 避免循环引用


def _import_soul() -> str:
    try:
        from app.agents.prompts import load_soul  # noqa: PLC0415
        return load_soul()
    except ImportError:
        logger.warning("Cannot import load_soul — using empty")
        return ""


def _import_memory() -> str:
    try:
        from app.agents.prompts import load_memory  # noqa: PLC0415
        return load_memory()
    except ImportError:
        logger.warning("Cannot import load_memory — using empty")
        return ""


def _import_user_memory(user_id: str) -> str:
    try:
        from app.agents.prompts import load_user_memory  # noqa: PLC0415
        return load_user_memory(user_id)
    except ImportError:
        logger.warning("Cannot import load_user_memory — using empty")
        return ""


def _import_safety_rules() -> str:
    try:
        from app.agents.prompts import load_safety_rules  # noqa: PLC0415
        return load_safety_rules()
    except ImportError:
        logger.warning("Cannot import load_safety_rules — using empty")
        return ""


def _import_project_agents_md() -> str:
    try:
        from app.agents.prompts import load_project_agents_md  # noqa: PLC0415
        return load_project_agents_md()
    except ImportError:
        return ""


def _import_skills_index() -> str:
    try:
        from app.agents.prompts import build_skills_index  # noqa: PLC0415
        return build_skills_index()
    except ImportError:
        return ""


def build_environment_hints(context: dict) -> str:
    """构建环境信息（时间/租户/语言）— 真实实现。"""
    parts: list[str] = []
    if "time" in context:
        parts.append(f"当前时间：{context['time']}")
    if "tenant" in context:
        parts.append(f"租户：{context['tenant']}")
    if "language" in context:
        parts.append(f"用户语言：{context['language']}")
    if not parts:
        return ""
    return "## 环境信息\n\n" + "\n".join(parts)


def load_agent_prompt(active_agent: str) -> str:
    """加载 Specialist Agent Prompt（screening.md / interview.md / ...）。

    使用 lazy import 避免与 __init__.py 循环引用。
    """
    try:
        from app.agents.prompts import load_prompt  # noqa: PLC0415
    except ImportError:
        logger.warning("Cannot import load_prompt — prompts module not initialized")
        return ""
    return load_prompt(active_agent)


# ── 主组装函数 ──


def build_layered_prompt(
    user_id: str,
    active_agent: str,
    context: dict | None = None,
    ephemeral: str | None = None,
) -> PromptBundle:
    """组装 9 层 PromptBundle。

    Args:
        user_id: HR 用户 ID（用于加载 per-user USER.md）
        active_agent: 当前激活的 Specialist Agent 名（screening/interview/...）
        context: 运行时上下文（time/tenant/language/...）
        ephemeral: 临时覆盖文本（调试 / A-B 测试用，env flag 控制）

    Returns:
        完整 PromptBundle，每层独立字段
    """
    ctx = context or {}
    return PromptBundle(
        soul=_import_soul(),
        memory=_import_memory(),
        user=_import_user_memory(user_id),
        project=_import_project_agents_md(),
        skills_index=_import_skills_index(),
        agent=load_agent_prompt(active_agent),
        safety=_import_safety_rules(),
        env=build_environment_hints(ctx),
        ephemeral=ephemeral or "",
    )


def assemble(bundle: PromptBundle) -> str:
    """把 9 段 PromptBundle 拼成最终 system prompt 字符串。

    规则：
    - 9 段按固定顺序拼接（SOUL → MEMORY → USER → PROJECT → AGENT → SAFETY → ENV → EPHEMERAL）
    - 跳过空字符串段
    - 分隔符：`\\n\\n---\\n\\n`（让 LLM 看到清晰段落）

    Returns:
        完整 system prompt 字符串（全空时返回 ""）
    """
    parts = [
        bundle.soul,
        bundle.memory,
        bundle.user,
        bundle.project,
        bundle.agent,
        bundle.safety,
        bundle.env,
        bundle.ephemeral,
    ]
    return "\n\n---\n\n".join(p for p in parts if p)
