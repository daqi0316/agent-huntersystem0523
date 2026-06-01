"""Agent 启动引导 — 在应用启动时初始化所有 Specialist Agent 并注册到 RouterAgent。

确保:
1. 所有 Agent 在 AgentRegistry 中可用（由 BaseAgent.__init__ 自动完成）
2. RouterAgent 持有所有意图 → Agent 的路由映射
3. get_router() 提供全局唯一的 RouterAgent 实例
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.agents.registry import AgentRegistry
from app.agents.router_agent import INTENT_TYPES as ROUTER_INTENT_TYPES

if TYPE_CHECKING:
    from app.agents.base import BaseAgent
    from app.agents.router_agent import RouterAgent

logger = logging.getLogger(__name__)

# ── 意图 → Agent 类型映射 ──
#
# 配对的 key 是 AgentRegistry 中注册的名称（BaseAgent.__init__ 自动推导）。
# RouterAgent.register_route(intent, agent) 用于建立路由。
#
_INTENT_AGENT_MAP: dict[str, str] = {
    "resume_parser": "resume_parser",
    "screening": "screening",
    "interview": "interview",
    "jd_generation": "sourcing",
    "candidate_search": "sourcing",
    "outreach": "sourcing",
    "channel_strategy": "sourcing",
    "offering": "offering",
    "onboarding": "onboarding",
    "analytics": "analytics",
    "report": "analytics",
}

# 全局 RouterAgent 实例（延迟初始化）
_router: RouterAgent | None = None


def _create_agent(agent_type: str) -> BaseAgent | None:
    """创建并注册一个 Agent 实例。

    利用 BaseAgent.__init__ 的自动注册机制，创建实例后
    AgentRegistry 中即可通过名称查找。
    """
    try:
        if agent_type == "resume_parser":
            from app.agents.resume_parser import ResumeParserAgent
            return ResumeParserAgent()
        elif agent_type == "screening":
            from app.agents.screening_agent import ScreeningAgent
            return ScreeningAgent()
        elif agent_type == "interview":
            from app.agents.interview_agent import InterviewAgent

            return InterviewAgent()
        elif agent_type == "sourcing":
            from app.agents.sourcing_agent import SourcingAgent

            return SourcingAgent()
        elif agent_type == "offering":
            from app.agents.offering_agent import OfferingAgent

            return OfferingAgent()
        elif agent_type == "onboarding":
            from app.agents.onboarding_agent import OnboardingAgent

            return OnboardingAgent()
        elif agent_type == "analytics":
            from app.agents.analytics_agent import AnalyticsAgent

            return AnalyticsAgent()
        else:
            logger.warning("Bootstrap: unknown agent_type '%s', skipping", agent_type)
            return None
    except Exception as e:
        logger.error("Bootstrap: failed to create agent '%s': %s", agent_type, e)
        return None


def _register_all_agents() -> list[str]:
    """初始化所有 Specialist Agent（自动注册到 AgentRegistry）。"""
    created: list[str] = []
    for agent_type in ("resume_parser", "screening", "interview", "sourcing", "offering", "onboarding", "analytics"):
        instance = _create_agent(agent_type)
        if instance is not None:
            created.append(agent_type)
            logger.debug("Bootstrap: created and registered agent '%s'", agent_type)
    return created


def _build_router(created: list[str]) -> RouterAgent:
    """构建 RouterAgent 并注册所有已初始化的 Agent 路由。"""
    from app.agents.router_agent import RouterAgent

    router = RouterAgent(name="bootstrap_router")

    registered_count = 0
    for intent, agent_type_name in _INTENT_AGENT_MAP.items():
        if agent_type_name not in created:
            continue
        agent = AgentRegistry.resolve(agent_type_name)
        if agent is None:
            logger.warning("Bootstrap: agent '%s' not found in Registry, skipping route '%s'", agent_type_name, intent)
            continue
        router.register_route(intent, agent)
        registered_count += 1
        logger.debug("Bootstrap: routed intent '%s' → agent '%s'", intent, agent_type_name)

    logger.info(
        "Bootstrap: RouterAgent initialized with %d/%d routes",
        registered_count,
        len(_INTENT_AGENT_MAP),
    )
    return router


def init_agents() -> RouterAgent:
    """初始化所有 Agent 并构建 RouterAgent。

    幂等设计：多次调用不会重复创建 Agent。
    """
    global _router
    if _router is not None:
        logger.debug("Bootstrap: already initialized, skipping")
        return _router

    logger.info("Bootstrap: initializing all specialist agents...")
    created = _register_all_agents()
    _router = _build_router(created)

    # 输出已注册的 Agent 列表
    registered = AgentRegistry.list_agents()
    logger.info("Bootstrap: AgentRegistry has %d entries: %s", len(registered), registered)

    return _router


def get_router() -> RouterAgent:
    """获取全局 RouterAgent 实例。

    如果尚未初始化则自动调用 init_agents()。
    """
    global _router
    if _router is None:
        return init_agents()
    return _router


def reset_for_testing() -> None:
    """测试用：重置全局状态。"""
    global _router
    _router = None
    AgentRegistry.clear()
