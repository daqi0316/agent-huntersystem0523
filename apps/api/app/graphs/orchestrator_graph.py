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
import json
import logging
from typing import Annotated, TypedDict, Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables import RunnableConfig

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


# Sub-task type → 实际 agent 名称
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


# Sub-task type descriptions (used in LLM prompt for decomposition)
_SUB_TASK_TYPES = {
    "screening": "简历初筛/筛选/筛",
    "interview": "面试安排/面试/面",
    "jd_generation": "JD 生成/职位描述",
    "knowledge_query": "知识库查询/查询",
    "candidate_search": "候选人搜索/搜索候选人",
    "report": "报告生成/报告/汇总",
    "offering": "Offer 发放/发offer/offer/录用",
    "onboarding": "入职流程/入职/onboard",
    "analytics": "数据分析/分析/统计",
    "screen_resume": "简历精筛/复筛/screen_resume",
}


# Keyword → sub-task type (fallback when LLM unavailable)
_GUESS_TYPE_KEYWORDS: dict[str, list[str]] = {
    "screening": ["筛选", "简历", "screen", "resume", "match", "初筛", "过滤"],
    "interview": ["面试", "安排", "interview", "schedule"],
    "jd_generation": ["jd", "职位描述", "generate jd", "job description"],
    "knowledge_query": ["知识库", "查询", "knowledge", "policy", "规则"],
    "candidate_search": ["搜索", "查找", "找候选人", "search", "find"],
    "report": ["报告", "汇总", "report", "summary"],
    "offering": ["offer", "录用", "薪资", "salary", "compensation"],
    "onboarding": ["入职", "onboard", "orientation"],
    "analytics": ["分析", "统计", "dashboard", "analytics", "指标"],
    "screen_resume": ["复筛", "精筛", "deep screen", "简历复筛", "简历精筛"],
}


_orchestrator_system_prompt: str | None = None


def _load_orchestrator_system_prompt() -> str:
    global _orchestrator_system_prompt
    if _orchestrator_system_prompt is None:
        try:
            from app.agents.prompts import load_prompt
            _orchestrator_system_prompt = load_prompt("orchestrator") or ""
        except Exception as e:
            logger.warning("Failed to load orchestrator system prompt: %s", e)
            _orchestrator_system_prompt = ""
    return _orchestrator_system_prompt


def _guess_type(text: str) -> str:
    text_lower = text.lower()
    for intent, keywords in _GUESS_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return intent
    return "screening"


async def _llm_json_chat(
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> dict | list | None:
    from app.llm import get_llm_client

    system_prompt = _load_orchestrator_system_prompt()
    try:
        llm = get_llm_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        reply = await llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
        if "```" in reply:
            parts = reply.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("{") or p.startswith("["):
                    reply = p
                    break
        start = reply.find("[") if "[" in reply else reply.find("{")
        end = reply.rfind("]") if "]" in reply else reply.rfind("}")
        if start != -1 and end != -1 and end > start:
            reply = reply[start: end + 1]
        return json.loads(reply)
    except Exception as e:
        logger.warning("Orchestrator LLM call failed: %s", e)
        return None


async def decompose_task(task: str, context: dict | None = None) -> list[dict]:
    if _load_orchestrator_system_prompt():
        context_str = f"\n上下文: {context}" if context else ""
        type_descriptions = "\n".join(f"- {k}: {v}" for k, v in _SUB_TASK_TYPES.items())
        user_prompt = (
            f"请将以下复杂任务分解为多个原子子任务。\n\n"
            f"复杂任务: 「{task}」{context_str}\n\n"
            f"子任务类型可用:\n{type_descriptions}\n\n"
            f"输出 JSON 数组，每个元素包含:\n"
            f'  {{"type": "子任务类型", "description": "具体做什么", "depends_on": [依赖的子任务索引]}}\n\n'
            f"示例:\n"
            f'[{{"type": "candidate_search", "description": "搜索候选人", "depends_on": []}},\n'
            f' {{"type": "screening", "description": "筛选简历", "depends_on": [0]}}]'
        )
        llm_out = await _llm_json_chat(user_prompt)
        if isinstance(llm_out, list) and len(llm_out) > 0:
            return llm_out

    logger.warning("LLM decompose failed, falling back to keyword")
    return [{"type": _guess_type(task), "description": task, "depends_on": []}]


def build_dag(sub_tasks: list[dict]) -> list[list[int]]:
    """Topological sort: layer sub-tasks by dependency (parallel levels)."""
    n = len(sub_tasks)
    in_degree = [0] * n
    dependents = [[] for _ in range(n)]
    for i, task in enumerate(sub_tasks):
        for dep in task.get("depends_on", []):
            if isinstance(dep, int) and dep < n and dep != i:
                dependents[dep].append(i)
                in_degree[i] += 1
    levels = []
    queue = [i for i in range(n) if in_degree[i] == 0]
    while queue:
        levels.append(list(queue))
        next_queue = []
        for node in queue:
            for dep in dependents[node]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    next_queue.append(dep)
        queue = next_queue
    executed = sum(len(l) for l in levels)
    if executed < n:
        levels.append([i for i in range(n) if i not in {j for l in levels for j in l}])
    return levels


def _needs_human_review(result: dict, task_type: str) -> bool:
    if task_type in ("interview", "offering"):
        return True
    status = result.get("status", "")
    if status in ("awaiting_approval", "pending_review"):
        return True
    if result.get("result", {}).get("needs_human_review"):
        return True
    return False


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
    return {
        "agent": agent_result.get("agent", task_type),
        "status": agent_result.get("status", "completed"),
        "summary": agent_result.get("summary", ""),
        "result": agent_result.get("result", {}),
        "details": agent_result.get("details", {}),
    }


def _build_sub_task_input(task_type: str, sub_task: dict, shared_context: dict) -> dict:
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

    调用 decompose_task() 获取 sub_tasks，
    再调 build_dag() 获取层级索引。
    失败时降级为单 sub-task 的单层 DAG。
    """
    text = state.get("input_text", "")
    if not text:
        return {"error": "no input_text for multi-stage", "status": "failed"}

    try:
        sub_tasks = await decompose_task(text, context=None)
        if not sub_tasks:
            sub_tasks = [{"type": "screening", "description": text, "depends_on": []}]
        levels = build_dag(sub_tasks)
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


async def _run_sub_task(
    sub_task: dict,
    shared_context: dict,
    user_id: str,
    thread_id: str | None = None,
) -> dict:
    """执行单个 sub-task。

    1. 解析 agent_name（_TYPE_TO_AGENT 映射）
    2. AgentRegistry.resolve → agent.run()，构造 shared_context-aware input
    3. 写回 shared_context
    4. 命中 _needs_human_review → HumanLoopAgent.create_proposal → awaiting_approval
       此时把 graph 的 thread_id 透传给 create_proposal，写入 Redis 索引
       （appr:graph_thread:{approval_id} → thread_id），让 PR-V.2 的 /resume 端点
       能从 approval_id 反查 thread_id，恢复 graph 状态。
    """
    task_type = sub_task.get("type", "chat")
    agent_name = _TYPE_TO_AGENT.get(task_type, task_type)

    try:
        from app.agents.registry import AgentRegistry

        agent = AgentRegistry.resolve(agent_name)
        if agent:
            input_data = _build_sub_task_input(task_type, sub_task, shared_context)
            agent_out = await agent.run(input_data)

            # 写回 shared_context
            _update_shared_context(shared_context, task_type, agent_out)

            # 检查是否需要人工审批
            if _needs_human_review(agent_out, task_type):
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
                        thread_id=thread_id,
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

    # Fallback — 失败时仍返回结构化结果
    return {
        "agent": task_type,
        "status": "failed",
        "summary": f"{task_type} 处理失败",
        "result": {},
        "details": {"error": "agent_not_found_or_failed"},
    }


async def _execute_level(
    state: OrchestratorState,
    config: RunnableConfig | None = None,
) -> dict:
    """并行执行当前 level 的所有 sub-tasks。

    - 用 asyncio.gather 跑当前 level 的 sub-tasks
    - 失败时记录到 results（不中断整个 level）
    - 命中 awaiting_approval → 设 paused_at_level → status=awaiting_approval
    - 否则 current_level += 1，状态保持 running

    PR-V.2: 把 graph 的 thread_id 从 RunnableConfig 透传给 _run_sub_task，
    让 HumanLoopAgent.create_proposal 写入 approval_id → thread_id 的 Redis 索引。
    """
    levels = state.get("levels") or []
    current_level = state.get("current_level", 0)
    sub_tasks = state.get("sub_tasks") or []
    shared_context = dict(state.get("shared_context") or {})
    existing_results = list(state.get("results") or [])
    user_id = state.get("user_id", "")

    thread_id = None
    if config and isinstance(config, dict):
        thread_id = (config.get("configurable") or {}).get("thread_id")

    # 边界处理
    if not levels or not sub_tasks or current_level >= len(levels):
        return {"status": "completed", "results": existing_results}

    if len(existing_results) != len(sub_tasks):
        # 修复长度不一致（防止上游出错）
        existing_results = [None] * len(sub_tasks)

    level_indices = levels[current_level]
    level_sub_tasks = [sub_tasks[i] for i in level_indices]

    # 并行执行当前 level 的所有子任务
    coros = [
        _run_sub_task(st, shared_context, user_id, thread_id=thread_id)
        for st in level_sub_tasks
    ]
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
