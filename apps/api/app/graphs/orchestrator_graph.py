"""Orchestrator StateGraph — 主编排图（支持 single intent + multi-stage DAG）。

每个 node 直接调用现有 Agent.run()，不做 subgraph 薄包装。
interrupt 触发后走现有 HumanLoop（ApprovalService）。

PR-V.1 (Phase V) — multi-stage DAG support:
  - 检测 multi-intent → multi_stage_decompose → execute_level (loop) → END
  - 每个 level 内的 sub-tasks 并行执行（asyncio.gather）
  - 子任务触发 awaiting_approval → paused_at_level + status=awaiting_approval → END
  - 审批通过后通过 LangGraph checkpointer 恢复（PR-V.2 处理 /resume 端点）
"""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated, TypedDict, Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.router_agent import RouterAgent

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# 状态定义
# ─────────────────────────────────────────────────────────────────────


class OrchestratorState(TypedDict):
    # 现有 single-intent 字段
    task_id: str
    user_id: str
    job_id: str
    intent: str
    input_text: str
    agent_result: dict | None
    error: str | None
    status: str
    # PR-V.1 multi-stage 字段
    multi_stage: bool
    sub_tasks: list[dict]
    current_level: int
    levels: list[list[int]]
    paused_at_level: int | None
    results: list[dict | None]
    shared_context: dict


# ─────────────────────────────────────────────────────────────────────
# Intent → 节点 映射（单意图）
# ─────────────────────────────────────────────────────────────────────


_INTENT_TO_NODE = {
    "resume_parser": "execute_resume_parser",
    "screening": "execute_screening",
    "interview": "execute_interview",
    "sourcing": "execute_sourcing",
    "jd_generation": "execute_sourcing",
    "candidate_search": "execute_sourcing",
    "offering": "execute_offering",
    "onboarding": "execute_onboarding",
    "analytics": "execute_analytics",
    "report": "execute_analytics",
    "knowledge_query": "end",
    "orchestrator": "end",
    "chat": "end",
    "settings": "end",
}


# Sub-task type → 实际 agent 名称（与 OrchestratorAgent._TYPE_TO_AGENT 保持一致）
_TYPE_TO_AGENT = {
    "jd_generation": "sourcing",
    "candidate_search": "sourcing",
    "outreach": "sourcing",
    "channel_strategy": "sourcing",
    "report": "analytics",
    "screening": "screening",
    "interview": "interview",
    "offering": "offering",
    "onboarding": "onboarding",
    "analytics": "analytics",
    "knowledge_query": "sourcing",
    "screen_resume": "screening",
}


# ─────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────


def _get_agent(agent_type: str):
    from app.agents.registry import AgentRegistry
    return AgentRegistry.resolve(agent_type)


def _is_multi_stage_text(text: str) -> bool:
    """用 RouterAgent.is_multi_intent 检测是否需要多阶段编排。"""
    if not text:
        return False
    try:
        router = RouterAgent()
        return bool(router.is_multi_intent(text))
    except Exception as e:
        logger.warning("is_multi_intent failed (%s), defaulting to False", e)
        return False


def _normalize_sub_task_result(task_type: str, agent_result: dict) -> dict:
    """把 agent.run() 的输出归一化到与 OrchestratorAgent.execute_sub_task() 一致的格式。"""
    return {
        "agent": agent_result.get("agent", task_type),
        "status": agent_result.get("status", "completed"),
        "summary": agent_result.get("summary", ""),
        "result": agent_result.get("result", {}),
        "details": agent_result.get("details", {}),
    }


def _build_sub_task_input(task_type: str, sub_task: dict, shared_context: dict) -> dict:
    """从 shared_context 注入 upstream 数据（与 OrchestratorAgent._build_agent_input 语义一致）。"""
    prefix = f"{task_type}."
    upstream = {
        k: v for k, v in (shared_context or {}).items()
        if not k.startswith(prefix)
    }
    return {
        "action": task_type,
        "task": sub_task.get("description", ""),
        "text": sub_task.get("description", ""),
        "context": dict(upstream),
        "intent": task_type,
        **upstream,
    }


def _update_shared_context(shared_context: dict, task_type: str, result: dict) -> None:
    """把 agent.output_keys 写回 shared_context（与 OrchestratorAgent._store_result 语义一致）。"""
    if not isinstance(shared_context, dict):
        return
    agent_result = result.get("result", {})
    prefix = f"{task_type}."
    if isinstance(agent_result, dict):
        for key in result.get("output_keys", []) or []:
            if key in agent_result:
                shared_context[prefix + key] = agent_result[key]
        shared_context[prefix + "full"] = agent_result
    else:
        shared_context[prefix + "full"] = agent_result


# ─────────────────────────────────────────────────────────────────────
# Single-intent 节点（现有逻辑）
# ─────────────────────────────────────────────────────────────────────


async def _intent_recognition(state: OrchestratorState) -> dict:
    text = state.get("input_text", "")

    # PR-V.1: 先检测 multi-stage — 命中则不走单意图分类
    if _is_multi_stage_text(text):
        return {"multi_stage": True, "status": "running"}

    try:
        from app.agents.bootstrap import get_router
        router = get_router()
        intent = await router.classify({"text": text})
    except Exception as e:
        logger.warning("Router classify failed (%s), falling back to 'chat'", e)
        intent = "chat"
    return {"intent": intent, "multi_stage": False, "status": "running"}


async def _execute_agent(state: OrchestratorState, agent_type: str) -> dict:
    agent = _get_agent(agent_type)
    if not agent:
        return {"error": f"Agent '{agent_type}' not found", "status": "failed"}

    try:
        result = await agent.run({
            "user_id": state.get("user_id", ""),
            "job_id": state.get("job_id", ""),
            "input_text": state.get("input_text", ""),
        })
        return {"agent_result": result, "status": "completed"}
    except Exception as e:
        logger.error("Agent %s failed: %s", agent_type, e)
        return {"error": str(e), "status": "failed"}


async def execute_resume_parser(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "resume_parser")


async def execute_screening(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "screening")


async def execute_interview(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "interview")


async def execute_sourcing(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "sourcing")


async def execute_offering(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "offering")


async def execute_onboarding(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "onboarding")


async def execute_analytics(state: OrchestratorState) -> dict:
    return await _execute_agent(state, "analytics")


# ─────────────────────────────────────────────────────────────────────
# PR-V.1 Multi-stage 节点
# ─────────────────────────────────────────────────────────────────────


async def _multi_stage_decompose(state: OrchestratorState) -> dict:
    """多阶段任务分解 + DAG 拓扑排序。

    调用 OrchestratorAgent.decompose() 获取 sub_tasks，
    再调 build_dag() 获取层级索引。
    失败时降级为单 sub-task 的单层 DAG。
    """
    text = state.get("input_text", "")
    if not text:
        return {"error": "no input_text for multi-stage", "status": "failed"}

    try:
        from app.agents.orchestrator_agent import OrchestratorAgent

        orch = OrchestratorAgent()
        sub_tasks = await orch.decompose(text, context=None)
        if not sub_tasks:
            sub_tasks = [{"type": "screening", "description": text, "depends_on": []}]
        levels = orch.build_dag(sub_tasks)
        if not levels:
            # build_dag on empty/tiny sub_tasks can return []; rebuild trivially
            levels = [list(range(len(sub_tasks)))]
    except Exception as e:
        logger.warning("multi_stage_decompose failed (%s), using single-task fallback", e)
        sub_tasks = [{"type": "screening", "description": text, "depends_on": []}]
        levels = [[0]]

    logger.info(
        "multi_stage_decompose: %d sub_tasks, %d levels",
        len(sub_tasks), len(levels),
    )
    return {
        "sub_tasks": sub_tasks,
        "levels": levels,
        "current_level": 0,
        "results": [None] * len(sub_tasks),
        "shared_context": {},
        "paused_at_level": None,
        "multi_stage": True,
        "status": "running",
    }


async def _run_sub_task(sub_task: dict, shared_context: dict, user_id: str) -> dict:
    """执行单个 sub-task，与 OrchestratorAgent.execute_sub_task 语义一致。

    1. 解析 agent_name（_TYPE_TO_AGENT 映射）
    2. AgentRegistry.resolve → agent.run()，构造 shared_context-aware input
    3. 写回 shared_context
    4. 命中 _needs_human_review → HumanLoopAgent.create_proposal → awaiting_approval
    """
    task_type = sub_task.get("type", "chat")
    agent_name = _TYPE_TO_AGENT.get(task_type, task_type)

    try:
        from app.agents.orchestrator_agent import OrchestratorAgent
        from app.agents.registry import AgentRegistry

        agent = AgentRegistry.resolve(agent_name)
        if agent:
            input_data = _build_sub_task_input(task_type, sub_task, shared_context)
            agent_out = await agent.run(input_data)

            # 写回 shared_context
            _update_shared_context(shared_context, task_type, agent_out)

            # 检查是否需要人工审批
            if OrchestratorAgent._needs_human_review(agent_out, task_type):
                try:
                    from app.agents.human_loop import HumanLoopAgent
                    hl = HumanLoopAgent()
                    proposal = await hl.create_proposal(
                        user_id=user_id,
                        action_type=task_type,
                        params={
                            "description": sub_task.get("description", ""),
                            "result": agent_out.get("result", {}),
                        },
                    )
                    return {
                        "agent": task_type,
                        "status": "awaiting_approval",
                        "summary": f"{task_type} 需人工审批",
                        "result": agent_out.get("result", {}),
                        "details": {"approval": proposal},
                    }
                except Exception as e:
                    logger.warning("HumanLoop pause failed for %s: %s", task_type, e)

            return _normalize_sub_task_result(task_type, agent_out)
    except Exception as e:
        logger.warning("Sub-task %s via AgentRegistry failed: %s", task_type, e)

    # Fallback — 失败时仍返回结构化结果（与 legacy 行为一致）
    return {
        "agent": task_type,
        "status": "failed",
        "summary": f"{task_type} 处理失败",
        "result": {},
        "details": {"error": "agent_not_found_or_failed"},
    }


async def _execute_level(state: OrchestratorState) -> dict:
    """并行执行当前 level 的所有 sub-tasks。

    - 用 asyncio.gather 跑当前 level 的 sub-tasks
    - 失败时记录到 results（不中断整个 level）
    - 命中 awaiting_approval → 设 paused_at_level → status=awaiting_approval
    - 否则 current_level += 1，状态保持 running
    """
    levels = state.get("levels") or []
    current_level = state.get("current_level", 0)
    sub_tasks = state.get("sub_tasks") or []
    shared_context = dict(state.get("shared_context") or {})
    existing_results = list(state.get("results") or [])
    user_id = state.get("user_id", "")

    # 边界处理
    if not levels or not sub_tasks or current_level >= len(levels):
        return {"status": "completed", "results": existing_results}

    if len(existing_results) != len(sub_tasks):
        # 修复长度不一致（防止上游出错）
        existing_results = [None] * len(sub_tasks)

    level_indices = levels[current_level]
    level_sub_tasks = [sub_tasks[i] for i in level_indices]

    # 并行执行当前 level 的所有子任务
    coros = [_run_sub_task(st, shared_context, user_id) for st in level_sub_tasks]
    level_outputs = await asyncio.gather(*coros, return_exceptions=True)

    # 合并到 results
    new_results = list(existing_results)
    has_awaiting = False
    has_failed = False
    for idx, raw in zip(level_indices, level_outputs):
        if isinstance(raw, Exception):
            new_results[idx] = {
                "agent": sub_tasks[idx].get("type", "unknown"),
                "status": "failed",
                "summary": f"执行异常: {str(raw)[:100]}",
                "result": {},
                "details": {"error": str(raw)},
            }
            has_failed = True
        else:
            new_results[idx] = raw
            status = raw.get("status") if isinstance(raw, dict) else ""
            if status == "awaiting_approval":
                has_awaiting = True
            elif status == "failed":
                has_failed = True

    next_state: dict[str, Any] = {
        "results": new_results,
        "shared_context": shared_context,
        "current_level": current_level + 1,
    }

    if has_awaiting:
        next_state["paused_at_level"] = current_level
        next_state["status"] = "awaiting_approval"
    elif has_failed and current_level + 1 >= len(levels):
        next_state["status"] = "partial"
    else:
        next_state["status"] = "running"

    return next_state


def _should_continue_or_pause(state: OrchestratorState) -> str:
    """execute_level 后的条件边：决定进入下一 level 还是 END。"""
    if state.get("error"):
        return "end"
    if state.get("paused_at_level") is not None:
        # 暂停 — 等待 PR-V.2 通过 /resume 端点恢复
        return "end"
    levels = state.get("levels") or []
    current_level = state.get("current_level", 0)
    if current_level >= len(levels):
        return "end"
    return "execute_level"


# ─────────────────────────────────────────────────────────────────────
# 路由
# ─────────────────────────────────────────────────────────────────────


def _decide_route(state: OrchestratorState) -> str:
    if state.get("multi_stage"):
        return "multi_stage_decompose"
    intent = state.get("intent", "")
    return _INTENT_TO_NODE.get(intent, "end")


# ─────────────────────────────────────────────────────────────────────
# 测试辅助
# ─────────────────────────────────────────────────────────────────────


def make_initial_orchestrator_state(
    task_id: str = "",
    user_id: str = "",
    job_id: str = "",
    input_text: str = "",
) -> OrchestratorState:
    """构造测试/调用方用的初始 OrchestratorState。"""
    return {
        "task_id": task_id,
        "user_id": user_id,
        "job_id": job_id,
        "intent": "",
        "input_text": input_text,
        "agent_result": None,
        "error": None,
        "status": "",
        "multi_stage": False,
        "sub_tasks": [],
        "current_level": 0,
        "levels": [],
        "paused_at_level": None,
        "results": [],
        "shared_context": {},
    }


# ─────────────────────────────────────────────────────────────────────
# 构造图
# ─────────────────────────────────────────────────────────────────────


def create_orchestrator_graph(checkpointer=None, with_interrupt: bool = True):
    """构造主编排图 — 同时支持 single intent 与 multi-stage DAG。"""
    builder = StateGraph(OrchestratorState)

    # single intent 节点
    builder.add_node("intent_recognition", _intent_recognition)
    builder.add_node("execute_resume_parser", execute_resume_parser)
    builder.add_node("execute_screening", execute_screening)
    builder.add_node("execute_interview", execute_interview)
    builder.add_node("execute_sourcing", execute_sourcing)
    builder.add_node("execute_offering", execute_offering)
    builder.add_node("execute_onboarding", execute_onboarding)
    builder.add_node("execute_analytics", execute_analytics)

    # PR-V.1 multi-stage 节点
    builder.add_node("multi_stage_decompose", _multi_stage_decompose)
    builder.add_node("execute_level", _execute_level)

    builder.set_entry_point("intent_recognition")

    # 路由: multi-stage vs single intent
    builder.add_conditional_edges(
        "intent_recognition",
        _decide_route,
        {
            "multi_stage_decompose": "multi_stage_decompose",
            "execute_resume_parser": "execute_resume_parser",
            "execute_screening": "execute_screening",
            "execute_interview": "execute_interview",
            "execute_sourcing": "execute_sourcing",
            "execute_offering": "execute_offering",
            "execute_onboarding": "execute_onboarding",
            "execute_analytics": "execute_analytics",
            "end": END,
        },
    )

    # multi-stage 流程：decompose → execute_level (loop) → END
    builder.add_edge("multi_stage_decompose", "execute_level")
    builder.add_conditional_edges(
        "execute_level",
        _should_continue_or_pause,
        {
            "execute_level": "execute_level",
            "end": END,
        },
    )

    # single intent 流程：执行节点 → END
    for node in [
        "execute_resume_parser", "execute_screening", "execute_interview",
        "execute_sourcing", "execute_offering", "execute_onboarding",
        "execute_analytics",
    ]:
        builder.add_edge(node, END)

    kwargs: dict[str, Any] = {"checkpointer": checkpointer or MemorySaver()}
    if with_interrupt:
        # single intent 的 HumanLoop 走 LangGraph native interrupt
        # multi-stage 的 HumanLoop 走 status check（避免双重暂停）
        kwargs["interrupt_before"] = [
            "execute_resume_parser", "execute_screening", "execute_interview",
            "execute_sourcing", "execute_offering", "execute_onboarding",
            "execute_analytics",
        ]

    return builder.compile(**kwargs)
