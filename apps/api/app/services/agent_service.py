"""统一招聘 Agent — 三层分发: Orchestrator → Router → 工具调用。

接收自然语言消息:
  Step 1: 多阶段任务检测 → OrchestratorAgent（复杂任务分解）
  Step 2: 意图分发 → RouterAgent → Specialist Agent（单意图专业任务）
  Step 3: 回退 → LLM 工具调用循环（通用对话）

工具定义来自 app/skills/ 下的可插拔插件。
内置招聘工具同样以 skill 形式注册。
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from app.llm import get_llm_client
from app.mcp.manager import mcp_manager
from app.skills import all_handlers as all_skill_handlers, all_tools as all_skill_tools
from app.tools import all_handlers as all_builtin_handlers, all_tools as all_builtin_tools

logger = logging.getLogger(__name__)


def _adapt_graph_result_to_legacy(graph_state: dict) -> dict:
    """Adapt new orchestrator_graph.ainvoke() output to legacy route_single() format.

    Phase V scaffolding (see .omo/plans/phase-v.md PR-V.3).
    When settings.use_orchestrator_graph=True, the single-intent path uses the
    new LangGraph state machine which returns OrchestratorState. This adapter
    maps that shape back to the legacy {agent, status, summary, result} format
    so _build_approval_response() and _summarize_orch_result() keep working.
    """
    intent = graph_state.get("intent", "") or "unknown"
    status = graph_state.get("status", "completed")
    error = graph_state.get("error")
    agent_result = graph_state.get("agent_result") or {}

    if error:
        return {
            "agent": intent,
            "status": "failed",
            "summary": f"Graph execution failed: {error}",
            "result": {},
        }

    legacy_status = status if status in ("completed", "no_handler", "awaiting_approval") else "completed"
    return {
        "agent": intent,
        "status": legacy_status,
        "summary": agent_result.get("summary", "") if isinstance(agent_result, dict) else "",
        "result": agent_result,
    }

_BUILTIN_INSTALL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "install_skill",
            "description": "安装一个新 Skill。当用户需要新的功能时，你应当生成对应的 skill 代码并安装。每次只能安装一个 tool。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "skill 目录名，如 ip_lookup"},
                    "description": {"type": "string", "description": "技能的人类可读描述"},
                    "tool_name": {"type": "string", "description": "工具函数名，如 lookup_ip"},
                    "tool_description": {"type": "string", "description": "工具的 LLM 描述"},
                    "handler_code": {"type": "string", "description": "异步处理函数的完整代码"},
                    "parameters": {"type": "object", "description": "工具的 parameters schema"},
                },
                "required": ["name", "description", "tool_name", "tool_description", "handler_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "列出当前已安装的所有 Skill。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_BUILTIN_TOOLS = all_builtin_tools() + _BUILTIN_INSTALL_TOOLS
_BUILTIN_TOOLS_END = len(all_builtin_tools())
_BUILTIN_HANDLERS: dict[str, callable] = {}

_BUILTIN_HANDLERS: dict[str, callable] = {}


async def _register_builtins():
    if _BUILTIN_HANDLERS:
        return
    from app.skills.installer import install_skill as _do_install, installed_list as _do_list
    _BUILTIN_HANDLERS.update({
        "install_skill": _do_install,
        "list_skills": _do_list,
    })
    _BUILTIN_HANDLERS.update(all_builtin_handlers())


def _get_tools() -> list[dict]:
    return _BUILTIN_TOOLS + all_skill_tools() + mcp_manager.get_all_tools()


def _get_handlers() -> dict[str, callable]:
    handlers = dict(_BUILTIN_HANDLERS)
    handlers.update(all_builtin_handlers())
    handlers.update(all_skill_handlers())
    for sid, state in mcp_manager._servers.items():
        for tool in state.tools_cache:
            name = tool.get("name")
            if name and name not in handlers:
                server_id = sid
                tool_name = name
                async def _mcp_handler(**kwargs):
                    return await mcp_manager.call_tool(server_id, tool_name, kwargs)
                handlers[name] = _mcp_handler
    return handlers


SYSTEM_PROMPT = """你是一个由多 Agent 编排驱动的 AI 招聘系统，而非单个 AI 个体。

底层由以下 Agent 集群组成：
- Orchestrator Agent（编排中枢）— 统一调度，自动将用户需求拆解为子任务并分发
- Sourcing Agent（寻源）— 候选人搜索、渠道策略、话术模板、JD 生成
- Screening Agent（初筛）— 简历筛选、多维评分、风险标记（无 LLM 时可规则降级）
- Interview Agent（面试）— 轮次规划、评价表生成、面试安排
- Offering Agent（Offer）— 薪酬计算、录用方案
- Onboarding Agent（入职）— 入职计划、里程碑管理
- Analytics Agent（数据）— 漏斗分析、KPI 报表

你的能力（通过 Agent 编排实现）：
- 搜索和查看候选人信息
- AI 简历初筛（评估候选人与职位的匹配度）
- 查看职位列表
- 生成职位描述（JD）
- 安排面试
- 查看招聘看板统计数据
- 知识库问答
- 查看评估报告
- 实时天气查询（如候选人所在城市天气）
- 互联网搜索（获取最新新闻、行业信息、技术动态等）
- **安装新技能**：当用户需要新的功能时，你可以使用 install_skill 动态创建并安装技能
- **列出已安装技能**：使用 list_skills 查看当前所有可用技能

注意事项：
- 对于招聘相关的具体需求（筛选、面试、JD 生成等），系统会自动调度对应的 Specialist Agent 处理
- 每次只调用一个工具，根据用户的意图选择最合适的工具
- 如果用户没有明确指定参数，可以根据上下文推断，或者主动询问
- 工具调用后，根据返回的数据生成自然语言回复
- 如果用户问的问题超出你的能力范围，**且该问题不属于招聘范畴**，你可以尝试：
  1. 使用 web_search 搜索答案
  2. 或者安装一个新的 Skill 来提供该能力
- 回复用中文
- 不要输出思考过程或推理步骤，直接给出答案"""


async def _load_and_merge_history(
    messages: list[dict],
    user_id: str | None,
    session_id: str | None,
    max_history: int = 20,
) -> list[dict]:
    """Load past conversation messages from DB and prepend to current messages.
    Returns the merged message list.
    """
    if not user_id or not session_id or not messages:
        return messages

    try:
        from app.core.database import AsyncSessionLocal
        from app.services.conversation_service import ConversationService

        async with AsyncSessionLocal() as db:
            svc = ConversationService(db)
            history = await svc.load_history_for_context(session_id, max_history)
            if history:
                logger.info(
                    "Loaded %d history messages for session %s",
                    len(history), session_id,
                )
                return history + messages
    except Exception as e:
        logger.warning("Failed to load conversation history (non-blocking): %s", e)

    return messages


async def _save_conversation_turn(
    user_message: str,
    reply: str,
    user_id: str | None,
    session_id: str | None,
    tool_calls: list[dict] | None = None,
    orchestrator_messages: list[dict] | None = None,
) -> None:
    """Save a user-assistant turn to the conversation store."""
    if not user_id or not session_id:
        return

    try:
        from app.core.database import AsyncSessionLocal
        from app.services.conversation_service import ConversationService

        async with AsyncSessionLocal() as db:
            svc = ConversationService(db)

            # Save user message
            await svc.add_message(session_id, user_id, "user", user_message)

            # Save assistant reply
            await svc.add_message(
                session_id, user_id, "assistant", reply,
                tool_calls=tool_calls,
            )

            # Optionally save orchestrator sub-task messages
            if orchestrator_messages:
                await svc.add_messages(orchestrator_messages)

            logger.info("Saved conversation turn for session %s", session_id)
    except Exception as e:
        logger.warning("Failed to save conversation turn (non-blocking): %s", e)


async def _ensure_session(
    user_id: str | None,
    session_id: str | None,
    first_message: str,
) -> tuple[str | None, str]:
    """Ensure a session exists. If session_id is None, create one.
    Returns (user_id, session_id).
    """
    if not user_id:
        return None, session_id or ""

    if session_id:
        return user_id, session_id

    try:
        from app.core.database import AsyncSessionLocal
        from app.services.conversation_service import ConversationService

        title = first_message[:80] + ("…" if len(first_message) > 80 else "")

        async with AsyncSessionLocal() as db:
            svc = ConversationService(db)
            session = await svc.create_session(user_id, title=title)
            logger.info("Auto-created session %s for user %s", session.id, user_id)
            return user_id, session.id
    except Exception as e:
        logger.warning("Failed to create session (non-blocking): %s", e)
        return user_id, session_id or ""


# ── Main Chat Loop ──

async def _inject_memory_context(
    system_content: str,
    user_id: str | None,
    messages: list[dict],
) -> str:
    """Inject cross-session memory context into the system prompt if available."""
    if not user_id or not messages:
        return system_content

    query = (messages[-1] or {}).get("content", "")
    if not query.strip():
        return system_content

    try:
        from app.core.database import AsyncSessionLocal
        from app.core.qdrant import get_qdrant
        from app.services.qdrant_service import QdrantService
        from app.core.config import settings

        qdrant_client = await get_qdrant()
        qdrant_svc = QdrantService(client=qdrant_client, collection=settings.qdrant_memory_collection)
        async with AsyncSessionLocal() as db:
            llm = get_llm_client()
            from app.services.summary_service import SummaryService
            summary_svc = SummaryService(db=db, llm=llm, qdrant=qdrant_svc)
            context = await summary_svc.get_injection_context(user_id, query)

            from app.services.memory_fact import MemoryFactService
            fact_svc = MemoryFactService(db)
            structured = await fact_svc.get_structured_context(user_id)

        result = system_content
        if context:
            logger.info("Narrative memory context injected for user %s", user_id)
            result += context
        if structured:
            logger.info("Structured memory context injected for user %s", user_id)
            result += structured

        return result
    except Exception as e:
        logger.warning("Memory injection failed (non-blocking): %s", e)

    return system_content


async def _background_summarize(
    messages: list[dict],
    user_id: str | None,
    session_id: str | None,
) -> None:
    """Background task: generate and store conversation summary."""
    if not user_id or not session_id:
        return
    try:
        from app.core.database import AsyncSessionLocal
        from app.core.qdrant import get_qdrant
        from app.services.qdrant_service import QdrantService
        from app.core.config import settings

        qdrant_client = await get_qdrant()
        qdrant_svc = QdrantService(client=qdrant_client, collection=settings.qdrant_memory_collection)
        async with AsyncSessionLocal() as db:
            llm = get_llm_client()
            from app.services.summary_service import SummaryService
            summary_svc = SummaryService(db=db, llm=llm, qdrant=qdrant_svc)
            summary = await summary_svc.generate(user_id, session_id, messages)
            if summary:
                logger.info(
                    "Background summary saved for session %s (len=%d)",
                    session_id,
                    len(summary),
                )
    except Exception as e:
        logger.warning("Background summary generation failed (non-blocking): %s", e)


async def _background_record_facts(
    user_id: str | None,
    session_id: str | None,
    tool_results: list[dict],
) -> None:
    """Background task: convert tool results into structured memory facts."""
    if not user_id or not session_id or not tool_results:
        return
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.memory_fact import MemoryFactService

        async with AsyncSessionLocal() as db:
            svc = MemoryFactService(db)
            for tr in tool_results:
                if "error" in tr:
                    continue
                await svc.record_tool_result(
                    user_id=user_id,
                    session_id=session_id,
                    tool_name=tr["tool"],
                    args=tr.get("args", {}),
                    result=tr.get("result"),
                )
    except Exception as e:
        logger.warning("Background structured fact recording failed (non-blocking): %s", e)


async def _background_record_preferences(
    user_id: str | None,
    session_id: str | None,
    messages: list[dict],
) -> None:
    """Extract user-stated preferences from the last user message and persist as facts."""
    if not user_id or not session_id or not messages:
        return

    try:
        from app.llm import get_llm_client as get_llm
        from app.models.memory_fact import MemoryFact
        from app.core.database import AsyncSessionLocal

        # Find the last user message
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content", "").strip():
                last_user_msg = m["content"].strip()
                break
        if not last_user_msg:
            return

        llm = get_llm()
        reply = await llm.chat(
            messages=[
                {"role": "system", "content": (
                    "你是一个偏好提取器。从用户的招聘对话中提取明确的偏好要求，"
                    "比如地点偏好、技能偏好、薪资期望等。"
                    "每个偏好输出一行，格式：prefers_xxx = value。"
                    "如果对话中没有明确的偏好，输出空字符串。"
                    "只输出偏好行，不要其他说明。"
                )},
                {"role": "user", "content": last_user_msg},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        if not reply or not reply.strip():
            return

        import re
        facts: list[MemoryFact] = []
        for line in reply.strip().split("\n"):
            m = re.match(r"prefers_(\w+)\s*=\s*(.+)", line.strip())
            if m:
                key, value = m.group(1), m.group(2).strip()
                facts.append(MemoryFact(
                    user_id=user_id,
                    session_id=session_id,
                    fact_type="preference",
                    verb=f"prefers_{key}",
                    object_value={"value": value},
                ))

        if not facts:
            return

        async with AsyncSessionLocal() as db:
            for fact in facts:
                db.add(fact)
            await db.commit()
            logger.info("Recorded %d preference(s) for user %s", len(facts), user_id)

    except Exception as e:
        logger.warning("Preference recording failed (non-blocking): %s", e)


def _format_agent_result(intent: str, routing_result: dict) -> str:
    """将 Specialist Agent 的返回格式化为自然语言回复。"""
    result = routing_result.get("result", {})
    if not isinstance(result, dict):
        return str(result)

    summary = result.get("summary") or result.get("message") or result.get("reply", "")
    if summary:
        return summary

    # Agent 特定的格式化
    if intent == "screening":
        score = result.get("overall_score", "N/A")
        gate = "通过" if result.get("gate_passed") else "未通过"
        return f"初筛结果: 综合评分 {score}/100，{gate}。"
    if intent == "interview":
        plan = result.get("plan", [])
        if plan:
            rounds = ", ".join(f"{p.get('round','?')}({p.get('label','?')})" for p in plan[:3])
            return f"已生成面试计划: {rounds} 等 {len(plan)} 轮面试。"
        return "已生成面试计划。"
    if intent == "offering":
        pkg = result.get("total_package", result.get("adjusted_total", 0))
        return f"薪酬方案: 总包 ¥{pkg:,}/年。"
    if intent == "onboarding":
        milestones = len(result.get("onboarding_plan", {}).get("milestones", []))
        return f"已生成入职计划，包含 {milestones} 个里程碑。"
    if intent == "analytics":
        funnel = result.get("funnel", {})
        if funnel:
            return f"数据分析: 投递 {funnel.get('applied',0)} → 初筛 {funnel.get('screened',0)} → 面试 {funnel.get('interviewed',0)} → Offer {funnel.get('offered',0)} → 入职 {funnel.get('hired',0)}。"
        kpi = result.get("kpi", {})
        if kpi:
            return f"KPI: 招聘周期 {kpi.get('time_to_fill_days',0)} 天, 成本/人 ¥{kpi.get('cost_per_hire',0):,}。"
        return "数据分析结果已生成。"
    if intent in ("sourcing", "jd_generation", "candidate_search", "outreach", "channel_strategy"):
        if "talent_map" in result:
            return f"人才 Mapping 完成: {result.get('total_targets',0)} 个目标公司。"
        if "templates" in result:
            return f"已生成触达话术模板，共 {len(result['templates'])} 个。"
        if "recommendations" in result:
            return f"渠道策略已生成，预算 ¥{result.get('total_budget',0):,}。"
        fallback = result.get("fallback", False)
        if fallback:
            return result.get("message", "JD 生成服务暂不可用。")
        return f"sourcing 结果已生成。"

    import json
    return json.dumps(result, ensure_ascii=False, default=str)


# ── Orchestrator 响应辅助函数 (v3 1.5) ──


def _extract_last_message(messages: list[dict]) -> str:
    """提取最后一条用户消息。"""
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content", "").strip():
            return m["content"].strip()
    return ""


def _summarize_orch_result(result: dict) -> str:
    """将 Orchestrator 结果汇总为自然语言回复。"""
    if result.get("status") == "awaiting_approval":
        return result.get("summary", "部分操作需要你的审批。")
    if result.get("status") in ("no_handler",):
        return ""  # fallback to LLM tool loop

    outputs = result.get("outputs", [])
    reply_parts = []
    for output in outputs:
        if isinstance(output, dict):
            summary = output.get("summary", "")
            if summary:
                reply_parts.append(summary)
    if reply_parts:
        return "\n".join(reply_parts)

    if result.get("status") == "completed":
        return f"任务完成，共 {result.get('total_sub_tasks', 0)} 个子任务。"
    if result.get("status") == "partial":
        return f"部分完成: {result.get('succeeded', 0)}/{result.get('total_sub_tasks', 0)} 个子任务成功。"
    return ""


def _extract_agent_actions(result: dict) -> list[dict]:
    """从编排结果中提取 agent_actions 列表。"""
    outputs = result.get("outputs", [])
    actions = []
    for o in outputs:
        if not isinstance(o, dict):
            continue
        action = {
            "agent": o.get("agent", ""),
            "status": o.get("status", ""),
            "summary": o.get("summary", ""),
        }
        # 附带 approval_id，前端用于 approve/resume
        if o.get("status") == "awaiting_approval":
            approval = (o.get("details") or {}).get("approval", {})
            if approval.get("approval_id"):
                action["approval_id"] = approval["approval_id"]
        actions.append(action)
    return actions


def _build_approval_response(result: dict) -> dict:
    """构建需要审批的返回格式。"""
    return {
        "reply": _summarize_orch_result(result),
        "tool_calls": [],
        "model": "orchestrator/awaiting_approval",
        "agent_actions": _extract_agent_actions(result),
    }


async def chat_with_tools(
    messages: list[dict],
    user_id: str | None = None,
    session_id: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: str | None = None,
) -> dict:
    """统一 Agent 对话入口：三层分发 → Orchestrator → Router → LLM 工具循环。

    Step 0: Conversation memory — 确保 Session + 加载历史消息
    Step 1: OrchestratorAgent — 统一处理所有用户消息
      1a: 多阶段检测 → Orchestrator.run() (decompose + DAG)
      1b: 单意图 → Orchestrator.route_single() (classify + Specialist Agent)
      1c: awaiting_approval → 返回审批响应
    Step 2: LLM tool-calling 循环（降级：chat / 未识别意图）
    Step 3: Conversation persistence — 保存本轮对话到 DB

    session_id is auto-created when None and returned in the response.
    """
    await _register_builtins()

    # Step 0: Conversation memory
    last_user_msg = _extract_last_message(messages)
    user_id, session_id = await _ensure_session(user_id, session_id, last_user_msg)
    messages = await _load_and_merge_history(messages, user_id, session_id)

    if last_user_msg:
        # Step 1: Orchestrator 统一处理 (Phase V PR-V.3 graph-based ainvoke)
        try:
            from app.graphs.orchestrator_graph import (
                create_orchestrator_graph,
                make_initial_orchestrator_state,
            )

            graph = create_orchestrator_graph(
                checkpointer=None,
                with_interrupt=False,
            )
            initial_state = make_initial_orchestrator_state(
                user_id=user_id or "",
                input_text=last_user_msg,
            )
            final_state = await graph.ainvoke(initial_state)
            result = _adapt_graph_result_to_legacy(final_state)

            # Handle awaiting_approval — 返回审批响应，不继续执行
            if result.get("status") == "awaiting_approval":
                logger.info("Task requires approval, returning approval response")
                approval_resp = _build_approval_response(result)
                await _save_conversation_turn(
                    last_user_msg, approval_resp.get("reply", ""), user_id, session_id
                )
                return {**approval_resp, "session_id": session_id}

            # Handle successful dispatch
            if result.get("status") != "no_handler":
                reply = _summarize_orch_result(result)
                if reply:
                    await _save_conversation_turn(last_user_msg, reply, user_id, session_id)
                    return {
                        "reply": reply,
                        "tool_calls": [],
                        "model": f"orchestrator/{result.get('status', 'completed')}",
                        "agent_actions": _extract_agent_actions(result),
                        "session_id": session_id,
                    }
        except Exception as e:
            logger.warning("Orchestrator failed, fallback to LLM tool loop: %s", e)

    llm = get_llm_client()
    tools = _get_tools()
    handlers = _get_handlers()

    system_content = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    system_content = await _inject_memory_context(system_content, user_id, messages)
    system_msg = {"role": "system", "content": system_content}
    msgs = [system_msg] + messages[-20:]

    # LLM 推理（带工具）
    response = await llm.client.chat.completions.create(
        model=llm.model,
        messages=msgs,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
        max_tokens=max_tokens,
    )

    choice = response.choices[0]
    reply = choice.message.content or ""
    tool_calls = choice.message.tool_calls or []

    # 依次执行工具调用
    tool_results = []
    for tc in tool_calls:
        fn = tc.function
        try:
            args = json.loads(fn.arguments)
            handler = handlers.get(fn.name)
            if handler:
                result = await handler(**args)
                tool_results.append({"tool": fn.name, "args": args, "result": result})
            else:
                tool_results.append({"tool": fn.name, "error": f"Unknown tool: {fn.name}"})
        except Exception as e:
            logger.error("Tool %s failed: %s", fn.name, e)
            tool_results.append({"tool": fn.name, "error": str(e)})

    # 如果有工具调用，把结果给 LLM 生成最终回复
    if tool_results:
        tool_messages = list(msgs)
        tool_call_stubs = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in tool_calls
        ]
        assistant_msg = {
            "role": "assistant",
            "content": reply or None,
            "tool_calls": tool_call_stubs,
        }
        tool_messages.append(assistant_msg)

        for idx, tr in enumerate(tool_results):
            tool_call_id = tool_call_stubs[idx]["id"] if idx < len(tool_call_stubs) else "unknown"
            if "error" in tr:
                content = json.dumps({"error": tr["error"]}, ensure_ascii=False)
            else:
                content = json.dumps(tr["result"], ensure_ascii=False, default=str)
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            })

        final = await llm.client.chat.completions.create(
            model=llm.model,
            messages=tool_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        reply = final.choices[0].message.content or ""

    # Step 3: Save conversation turn
    await _save_conversation_turn(last_user_msg, reply, user_id, session_id)

    if session_id and user_id:
        asyncio.create_task(_background_summarize(messages, user_id, session_id))
        asyncio.create_task(_background_record_facts(user_id, session_id, tool_results))
        asyncio.create_task(_background_record_preferences(user_id, session_id, messages))

    return {
        "reply": reply,
        "tool_calls": [
            {"name": t["tool"], "args": t.get("args", {}), "error": t.get("error")}
            for t in tool_results
        ],
        "model": llm.model,
        "session_id": session_id,
    }
