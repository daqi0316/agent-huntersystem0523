"""统一招聘 Agent — 三层分发: Orchestrator → Router → 工具调用。

接收自然语言消息:
  Step 1: 多阶段任务检测 → orchestrator_graph（复杂任务分解 + DAG）
  Step 2: 意图分发 → RouterAgent → Specialist Agent（单意图专业任务）
  Step 3: 回退 → LLM 工具调用循环（通用对话）
"""

from app.core.prompts import SYSTEM_PROMPT


import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from app.llm import get_llm_client
from app.llm.retry import llm_chat_with_retry
from app.mcp.manager import mcp_manager
from app.skills import all_handlers as all_skill_handlers, all_tools as all_skill_tools
from app.tools import all_handlers as all_builtin_handlers, all_tools as all_builtin_tools
from app.tools.metadata import get_metadata, get_max_retries, should_escalate, EscalationMode

from app.commands import CommandContext, CommandResult, CommandErrorCode
from app.commands.executor import CommandExecutor
from app.commands.registry import get_default_registry, register_all

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

SKILLS_ENABLED = os.getenv("SKILLS_ENABLED", "false").lower() == "true"

_tool_registry = None

def _get_tool_registry():
    global _tool_registry
    if _tool_registry is None:
        from app.agents.prompts import tool_registry
        _tool_registry = tool_registry
        if SKILLS_ENABLED:
            _tool_registry.enable_skills()
        else:
            _tool_registry.disable_skills()
    return _tool_registry

def _get_skill_tool_schemas() -> list[dict]:
    return _get_tool_registry().get_tools_schema("openai")

def _get_skill_tool_handlers() -> dict[str, callable]:
    reg = _get_tool_registry()
    if not reg.is_skills_enabled():
        return {}
    return {"load_skill": _skill_tool_handler}

async def _skill_tool_handler(name: str) -> str:
    return await _get_tool_registry().call_tool("load_skill", {"name": name})


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
    tools = _BUILTIN_TOOLS + all_skill_tools() + mcp_manager.get_all_tools()
    if SKILLS_ENABLED:
        tools = tools + _get_skill_tool_schemas()
    return tools


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
    if SKILLS_ENABLED:
        handlers.update(_get_skill_tool_handlers())
    return handlers


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


def _build_tool_messages_manually(
    base_msgs: list[dict],
    reply: str,
    tool_calls: list,
    tool_results: list[dict],
) -> list[dict]:
    """Build tool-call + tool-result message chain without ContextBuilder."""
    msgs = list(base_msgs)
    tool_call_stubs = [
        {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        }
        for tc in tool_calls
    ]
    msgs.append({
        "role": "assistant",
        "content": reply or None,
        "tool_calls": tool_call_stubs,
    })
    for idx, tr in enumerate(tool_results):
        tool_call_id = tool_call_stubs[idx]["id"] if idx < len(tool_call_stubs) else "unknown"
        if "error" in tr:
            content = json.dumps({"error": tr["error"]}, ensure_ascii=False)
        else:
            content = json.dumps(tr["result"], ensure_ascii=False, default=str)
        msgs.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })
    return msgs


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
    attachment: dict | None = None,
    command_context: CommandContext | None = None,
) -> dict:
    """统一 Agent 对话入口：三层分发 → Orchestrator → Router → LLM 工具循环。

    Step 0: Conversation memory — 确保 Session + 加载历史消息
    Step 1: orchestrator_graph — 统一处理所有用户消息
      1a: 多阶段检测 → create_orchestrator_graph().ainvoke() (decompose + DAG)
      1b: 单意图 → intent_recognition → execute_<agent>
      1c: awaiting_approval → 返回审批响应
    Step 2: LLM tool-calling 循环（降级：chat / 未识别意图）
    Step 3: Conversation persistence — 保存本轮对话到 DB

    session_id is auto-created when None and returned in the response.
    """
    await _register_builtins()

    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content", "").strip():
            last_user_msg = m["content"].strip()
            break

    if last_user_msg and last_user_msg.strip().startswith("/"):
        registry = get_default_registry()
        executor = CommandExecutor(registry=registry)
        ctx = CommandContext(
            session_id=session_id or "",
            user_id=user_id or "",
            permissions=command_context.permissions if command_context else [],
            user_role=command_context.user_role if command_context else None,
        )
        result = await executor.execute(last_user_msg.strip(), ctx)
        if result.action == "passthrough":
            pass
        else:
            return {
                "reply": result.message,
                "tool_calls": [],
                "model": "",
                "session_id": session_id,
            }

    if last_user_msg:
        if attachment:
            att = attachment
            last_user_msg = (
                f"{last_user_msg}\n\n[附件文件]\n"
                f"文件名: {att.get('filename', 'resume')}\n"
                f"类型: {att.get('file_type', 'pdf')}\n"
                f"路径: {att.get('file_url', '')}\n"
                f"请调用 parse_resume 工具解析此文件，file_url 为 {att.get('file_url', '')}，file_type 为 {att.get('file_type', '')}，filename 为 {att.get('filename', '')}。"
            )
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
    msgs = [system_content] if system_content else []

    cb = None
    try:
        from app.core.context_builder import ContextBuilder
        from app.core.qdrant import get_qdrant
        qdrant_client = await get_qdrant()
        async with AsyncSessionLocal() as db:
            cb = ContextBuilder(
                db=db,
                llm=llm,
                qdrant=QdrantService(client=qdrant_client, collection=getattr(settings, "qdrant_memory_collection", "memory")) if qdrant_client else None,
                model=llm.model,
            )
            msgs = await cb.build(user_id, messages[-20:])
    except Exception as e:
        logger.warning("ContextBuilder.build() failed: %s, using fallback", e)
        system_msg = {"role": "system", "content": system_content}
        msgs = [system_msg] + messages[-20:]

    # LLM 推理（带工具，指数退避重试）
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            response = await llm.client.chat.completions.create(
                model=llm.model,
                messages=msgs,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                delay = 1.0 * (2 ** attempt)
                logger.warning("LLM call failed (attempt %d/3): %s, retrying in %.1fs...", attempt + 1, e, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("LLM call failed after 3 attempts: %s", e)
                raise last_err from None

    choice = response.choices[0]
    reply = choice.message.content or ""
    tool_calls = choice.message.tool_calls or []

    # 执行工具调用（含重试 + escalation 策略）
    tool_results = []
    for tc in tool_calls:
        fn = tc.function
        tool_name = fn.name
        meta = get_metadata(tool_name)
        max_retries = get_max_retries(tool_name)
        escalation = should_escalate(tool_name)

        last_error = None
        succeeded = False

        for attempt in range(max_retries + 1):
            try:
                args = json.loads(fn.arguments)
                handler = handlers.get(tool_name)
                if not handler:
                    last_error = f"Unknown tool: {tool_name}"
                    break
                result = await handler(**args)
                if isinstance(result, dict) and result.get("status") == "failed":
                    err = result.get("error", {})
                    err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    if attempt < max_retries and meta.retryable:
                        logger.warning("Tool %s attempt %d failed (retriable): %s — retrying", tool_name, attempt + 1, err_msg)
                        last_error = err_msg
                        await asyncio.sleep(0.25 * (attempt + 1))
                        continue
                    else:
                        last_error = err_msg
                else:
                    succeeded = True
                    tool_results.append({"tool": tool_name, "args": args, "result": result, "needs_human": escalation != EscalationMode.NONE})
                    break
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries and meta.retryable:
                    logger.warning("Tool %s exception attempt %d: %s — retrying", tool_name, attempt + 1, last_error)
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                break

        if not succeeded and last_error is not None:
            logger.error("Tool %s exhausted retries (or non-retryable): %s", tool_name, last_error)
            tool_results.append({"tool": tool_name, "args": json.loads(fn.arguments) if fn.arguments else {}, "error": last_error, "needs_human": escalation != EscalationMode.NONE})

    # 如果有工具调用，把结果给 LLM 生成最终回复
    if tool_results:
        if cb is not None:
            try:
                msgs2 = await cb.build_with_tools(
                    user_id, messages, reply, tool_calls, tool_results
                )
            except Exception as e:
                logger.warning("Second build_with_tools failed: %s", e)
                msgs2 = _build_tool_messages_manually(msgs, reply, tool_calls, tool_results)
        else:
            msgs2 = _build_tool_messages_manually(msgs, reply, tool_calls, tool_results)
        final = await llm.client.chat.completions.create(
            model=llm.model,
            messages=msgs2,
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
            {
                "name": t["tool"],
                "args": t.get("args", {}),
                "error": t.get("error"),
                "needs_human": t.get("needs_human", False),
            }
            for t in tool_results
        ],
        "model": llm.model,
        "session_id": session_id,
    }
