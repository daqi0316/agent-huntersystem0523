"""OrchestratorAgent — 复杂任务分解与编排执行。

接收复杂请求 → 分解为原子子任务 → 按依赖图并行/串行执行 →
聚合各 Agent 结果 → 返回综合响应。
使用 prompts/orchestrator.md 作为 system_prompt。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.router_agent import RouterAgent
from app.llm import get_llm_client

logger = logging.getLogger(__name__)

_MULTI_STAGE_KEYWORDS = [
    "然后", "并且", "同时", "之后", "接着",
    "先", "再", "首先", "最后",
    "并",
    "and", "then", "also", "after", "meanwhile", "next",
]

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


class OrchestratorAgent(BaseAgent):
    """编排 Agent — 任务分解 + DAG 调度 + 结果聚合 (LLM 优先, 规则兜底)。"""

    output_keys = ["outputs", "sub_tasks"]

    def __init__(self, name: str = "orchestrator"):
        super().__init__(name)
        self.router = RouterAgent()
        self._llm = None
        self.shared_context: dict[str, Any] = {}

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    async def ensure_llm(self):
        if self._llm is None:
            self._llm = get_llm_client()

    # ── LLM 辅助 ──

    async def _llm_json_chat(self, user_prompt: str, temperature: float = 0.2, max_tokens: int = 1024) -> dict | list | None:
        """调用 LLM（system_prompt from prompts/orchestrator.md）并解析 JSON。"""
        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            reply = await self.llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
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
            logger.warning("OrchestratorAgent LLM call failed: %s", e)
            return None

    # ── 任务分解（LLM 优先） ──

    async def decompose(self, task: str, context: dict | None = None) -> list[dict]:
        """LLM 分解复杂任务为子任务列表（使用 self.system_prompt），失败降级关键词。"""
        if self.system_prompt:
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
            llm_out = await self._llm_json_chat(user_prompt)
            if isinstance(llm_out, list) and len(llm_out) > 0:
                return llm_out

        # 关键词降级
        logger.warning("LLM decompose failed, falling back to keyword")
        return [{"type": self.guess_type(task), "description": task, "depends_on": []}]

    # ── 子任务执行 ──

    async def execute_sub_task(self, task: dict) -> dict:
        """执行单个子任务。

        1. AgentRegistry.resolve(agent_name) — 通过 _TYPE_TO_AGENT 映射后路由
        2. _build_agent_input — 从 shared_context 注入 upstream 数据
        3. _store_result — 声明式写回 shared_context
        4. 失败降级 _execute_service_task
        """
        task_type = task.get("type", "chat")
        description = task.get("description", "")

        agent_name = task_type
        if agent_name in _TYPE_TO_AGENT:
            agent_name = _TYPE_TO_AGENT[agent_name]

        # 1. AgentRegistry.resolve(agent_name) — 映射后路由到 Specialist Agent
        try:
            from app.agents.registry import AgentRegistry

            agent = AgentRegistry.resolve(agent_name)
            if agent:
                input_data = self._build_agent_input(task_type, task)
                result = await agent.run(input_data)
                self._store_result(agent, task_type, result)

                # v3 1.3 — Human-in-the-Loop 暂停
                if self._needs_human_review(result, task_type):
                    try:
                        from app.agents.human_loop import HumanLoopAgent
                        hl = HumanLoopAgent()
                        proposal = await hl.create_proposal(
                            action_type=task_type,
                            params={
                                "description": description,
                                "result": result.get("result", {}),
                            },
                        )
                        return {
                            "agent": task_type,
                            "status": "awaiting_approval",
                            "summary": f"{task_type} 需人工审批",
                            "result": result.get("result", {}),
                            "details": {"approval": proposal},
                        }
                    except Exception as e:
                        logger.warning("HumanLoop pause failed for %s: %s", task_type, e)

                return {
                    "agent": result.get("agent", task_type),
                    "status": result.get("status", "completed"),
                    "summary": result.get("summary", ""),
                    "result": result.get("result", {}),
                    "details": result.get("details", {}),
                }
        except Exception as e:
            logger.warning("AgentRegistry.resolve(%s) failed: %s", task_type, e)

        # 2. 降级到 Service 调用，输出统一格式
        try:
            service_result = await self._execute_service_task(task_type, description)
            return {
                "agent": service_result.get("type", task_type),
                "status": service_result.get("status", "completed"),
                "summary": service_result.get("result", {}).get("summary", f"{task_type} 任务已完成"),
                "result": service_result.get("result", {}),
                "details": {"source": service_result.get("source", "service/unknown")},
            }
        except Exception as e:
            return {
                "agent": task_type,
                "status": "failed",
                "summary": f"{task_type} 处理失败: {str(e)[:100]}",
                "result": {},
                "details": {"error": str(e)},
            }

    async def _execute_service_task(self, task_type: str, description: str) -> dict:
        """Service 降级执行。"""
        if task_type in ("screening", "screen_resume"):
            from app.services.screening import ScreeningService
            return {
                "type": task_type, "description": description,
                "status": "completed",
                "result": {"summary": f"筛选任务: {description[:100]}", "status": "pending"},
                "source": f"service/{task_type}",
            }
        elif task_type == "jd_generation":
            from app.services.jd_generator import JDGeneratorService
            service = JDGeneratorService()
            result = await service.generate_jd(
                title=description[:100] or "职位", requirements=description, auto_improve=False,
            )
            return {
                "type": "jd_generation", "description": description, "status": "completed",
                "result": result, "source": "service/jd_generator",
            }
        elif task_type in ("candidate_search", "offering", "onboarding", "analytics", "report", "knowledge_query"):
            return {
                "type": task_type, "description": description, "status": "completed",
                "result": {"summary": f"已处理: {description[:100]}", "task_type": task_type},
                "source": "service/stub",
            }
        else:
            return {
                "type": task_type, "description": description, "status": "completed",
                "result": {"summary": f"已处理: {description[:100]}"},
                "source": "service/unknown",
            }

    # ── DAG 拓扑排序 ──

    def build_dag(self, sub_tasks: list[dict]) -> list[list[int]]:
        """拓扑排序：将子任务按依赖关系分层（并行层级）。"""
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

    # ── 子任务辅助 ──

    def _build_agent_input(self, task_type: str, task: dict) -> dict:
        """从 shared_context 和 task 构建 Agent 输入（排除自身 namespace 的键）。"""
        prefix = f"{task_type}."
        upstream = {
            k: v for k, v in self.shared_context.items()
            if not k.startswith(prefix)
        }
        return {
            "action": task_type,
            "task": task.get("description", ""),
            "text": task.get("description", ""),
            "context": dict(upstream),
            "intent": task_type,
            **upstream,
        }

    def _store_result(self, agent: BaseAgent, task_type: str, result: dict) -> None:
        """声明式写回 shared_context。"""
        agent_result = result.get("result", {})
        if isinstance(agent_result, dict):
            prefix = f"{task_type}."
            for key in getattr(agent, "output_keys", []):
                if key in agent_result:
                    self.shared_context[prefix + key] = agent_result[key]
            self.shared_context[prefix + "full"] = agent_result
        else:
            self.shared_context[f"{task_type}.full"] = agent_result

    @staticmethod
    def _needs_human_review(result: dict, task_type: str) -> bool:
        """判断结果是否需要人工审批。"""
        if task_type in ("interview", "offering"):
            return True
        status = result.get("status", "")
        if status in ("awaiting_approval", "pending_review"):
            return True
        if result.get("result", {}).get("needs_human_review"):
            return True
        return False

    # ── 关键词降级 ──

    def is_multi_stage(self, text: str) -> bool:
        """判断用户输入是否包含多阶段任务。"""
        text_lower = text.lower()
        for kw in _MULTI_STAGE_KEYWORDS:
            if kw in text_lower:
                return True
        hit_count = 0
        for type_name, description in _SUB_TASK_TYPES.items():
            candidates = [type_name.lower()] + [d.strip().lower() for d in description.split("/")]
            for c in candidates:
                if c in text_lower:
                    hit_count += 1
                    if hit_count >= 2:
                        return True
                    break
        return False

    def guess_type(self, text: str) -> str:
        """关键词推测子任务类型（降级用）。"""
        keyword_map: dict[str, list[str]] = {
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
        text_lower = text.lower()
        for intent, keywords in keyword_map.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    return intent
        return "screening"

    # ── 单意图快捷路由 ──

    async def route_single(self, input_data: dict) -> dict:
        """单意图快捷路由 — classify + AgentRegistry.resolve → run()。

        不走 decompose/DAG，直接分类 → 分发到对应 Specialist Agent。
        返回统一格式 output 列表（1 个元素），以便 chat_with_tools 统一处理。
        """
        from app.agents.registry import AgentRegistry

        text = input_data.get("text", "")
        intent = await self.router.classify(input_data)

        agent = AgentRegistry.resolve(intent)
        if agent:
            try:
                from app.agents.param_extractor import extract_params

                params = extract_params(text, intent)
                enriched = {**input_data, **params}
            except Exception:
                logger.warning("Param extraction failed, using raw input", exc_info=True)
                enriched = input_data

            result = await agent.run(enriched)
            return {
                "agent": result.get("agent", intent),
                "status": result.get("status", "completed"),
                "summary": result.get("summary", ""),
                "result": result.get("result", {}),
                "details": result.get("details", {}),
                "outputs": [result],
                "total_sub_tasks": 1,
                "succeeded": 1 if result.get("status") == "completed" else 0,
                "failed": 0,
                "intent": intent,
            }

        # intent 为 chat 或未识别 → 返回 no_handler，chat_with_tools 降级到 LLM 循环
        return {
            "agent": self.name,
            "status": "no_handler",
            "summary": f"意图: {intent}",
            "result": {},
            "details": {"intent": intent},
            "outputs": [],
            "total_sub_tasks": 0,
            "succeeded": 0,
            "failed": 0,
            "intent": intent,
        }

    # ── 主入口 ──

    async def run(self, input_data: dict) -> dict:
        """分解 → DAG 编排 → 聚合。

        支持两种模式：
        1. 传统路由：intent → router_agent
        2. 编排模式：task 字段 → 分解执行
        """
        task = input_data.get("task", input_data.get("message", ""))
        context = input_data.get("context")

        if not task:
            intent = input_data.get("intent", "agent")
            target = self.router.route(intent)
            result = await target.run(input_data)
            return self.format_result("completed", result, f"路由到 {intent} 完成", details={"intent": intent})

        start_time = datetime.now(timezone.utc)

        self.shared_context = {}
        sub_tasks = await self.decompose(task, context)
        levels = self.build_dag(sub_tasks)
        results = [None] * len(sub_tasks)

        for level in levels:
            coros = [self.execute_sub_task(sub_tasks[i]) for i in level]
            level_results = await asyncio.gather(*coros, return_exceptions=True)
            for i, raw in zip(level, level_results):
                if isinstance(raw, Exception):
                    results[i] = {
                        "agent": sub_tasks[i].get("type", "unknown"),
                        "status": "failed",
                        "summary": f"执行异常: {str(raw)[:100]}",
                        "result": {},
                        "details": {"error": str(raw)},
                    }
                else:
                    results[i] = raw

        succeeded = sum(1 for r in results if r and r.get("status") == "completed")
        failed = sum(1 for r in results if r and r.get("status") == "failed")
        awaiting = sum(1 for r in results if r and r.get("status") == "awaiting_approval")
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        if awaiting > 0:
            status = "awaiting_approval"
            summary = f"编排等待审批: {awaiting} 个子任务待确认 ({duration:.1f}s)"

            try:
                from app.agents.orchestrator_session import OrchestratorSession

                approval_ids = []
                for r in results:
                    if r and r.get("status") == "awaiting_approval":
                        aid = (r.get("details") or {}).get("approval", {}).get("approval_id", "")
                        if aid:
                            approval_ids.append(aid)

                session = OrchestratorSession()
                session.task = task
                session.context = context or {}
                session.sub_tasks = sub_tasks
                session.levels = levels
                session.results = results
                session.shared_context = dict(self.shared_context)
                session.paused_at_level = len(levels) - 1
                session.approval_ids = approval_ids
                await session.save()
            except Exception as e:
                logger.warning("Failed to save orchestrator session: %s", e)

        elif failed == 0:
            status = "completed"
            summary = f"编排全部完成 ({duration:.1f}s)"
        else:
            status = "partial"
            summary = f"编排部分完成: {succeeded}/{len(sub_tasks)} ({duration:.1f}s)"

        return {
            "agent": self.name,
            "status": status,
            "summary": summary,
            "result": {"outputs": results, "sub_tasks": sub_tasks},
            "total_sub_tasks": len(sub_tasks),
            "succeeded": succeeded,
            "failed": failed,
            "awaiting_approval": awaiting,
            "duration_seconds": round(duration, 2),
            "outputs": results,
            "sub_tasks": sub_tasks,
            "details": {"total": len(sub_tasks), "succeeded": succeeded, "failed": failed, "awaiting_approval": awaiting, "duration_seconds": round(duration, 2)},
        }


def get_orchestrator(mode: str = "auto", agents: list[BaseAgent] | None = None) -> OrchestratorAgent | PipelineOrchestrator | SequentialOrchestrator:
    """工厂函数 — 返回合适的编排器实例。

    Args:
        mode: "auto" → OrchestratorAgent (LLM 分解),
              "pipeline" → PipelineOrchestrator (固定流水线),
              "sequential" → SequentialOrchestrator (顺序执行).
        agents: 仅用于 pipeline/sequential 模式。
    """
    if mode == "pipeline":
        return PipelineOrchestrator(agents or [])
    elif mode == "sequential":
        return SequentialOrchestrator(agents or [])
    return OrchestratorAgent()


class PipelineOrchestrator(BaseAgent):
    """固定流水线编排器 — 按预设顺序依次执行各 Agent。

    每个 Agent 的输出会通过 output_keys 注入到下一个 Agent 的 shared_context。
    """

    output_keys = ["stages"]

    def __init__(self, agents: list[BaseAgent], name: str = "pipeline"):
        super().__init__(name)
        self._stages = agents

    async def run(self, input_data: dict) -> dict:
        shared_context: dict[str, Any] = dict(input_data)
        stage_outputs: list[dict] = []

        for idx, agent in enumerate(self._stages):
            stage_name = agent.name
            logger.info("[Pipeline] Stage %d/%d: %s", idx + 1, len(self._stages), stage_name)
            try:
                result = await agent.run(shared_context)

                if not isinstance(result, dict):
                    result = {"agent": stage_name, "status": "completed", "result": result}

                stage_outputs.append({
                    "stage": stage_name,
                    "status": result.get("status", "completed"),
                    "summary": result.get("summary", ""),
                })

                # 通过 output_keys 传播上下文
                agent_result = result.get("result", {})
                if isinstance(agent_result, dict):
                    for key in getattr(agent, "output_keys", []):
                        if key in agent_result:
                            ctx_key = f"{stage_name}.{key}"
                            shared_context[ctx_key] = agent_result[key]

            except Exception as e:
                logger.error("[Pipeline] Stage %s failed: %s", stage_name, e)
                stage_outputs.append({"stage": stage_name, "status": "failed", "error": str(e)})
                break

        return self.format_result(
            "completed",
            {"stages": stage_outputs, "shared_context": shared_context},
            f"流水线完成: {len(stage_outputs)} 阶段",
            details={"total_stages": len(self._stages), "completed": len(stage_outputs)},
        )


class SequentialOrchestrator(BaseAgent):
    """顺序编排器 — 通过 AgentRegistry 按名称依次执行 Agent。

    每个 Agent 的 result 中对应 output_keys 的字段会传递到下一个 Agent。
    """

    output_keys = ["results"]

    def __init__(self, agent_names: list[str], name: str = "sequential"):
        super().__init__(name)
        self._agent_names = agent_names

    async def run(self, input_data: dict) -> dict:
        from app.agents.registry import AgentRegistry

        shared_context: dict[str, Any] = dict(input_data)
        results: list[dict] = []

        for agent_name in self._agent_names:
            agent = AgentRegistry.resolve(agent_name)
            if agent is None:
                logger.warning("[Sequential] Agent '%s' not found, skipping", agent_name)
                results.append({"agent": agent_name, "status": "skipped", "error": "not_found"})
                continue

            logger.info("[Sequential] Running: %s", agent_name)
            try:
                result = await agent.run(shared_context)
                results.append({
                    "agent": agent_name,
                    "status": result.get("status", "completed"),
                    "summary": result.get("summary", ""),
                })

                agent_result = result.get("result", {})
                if isinstance(agent_result, dict):
                    for key in getattr(agent, "output_keys", []):
                        if key in agent_result:
                            ctx_key = f"{agent_name}.{key}"
                            shared_context[ctx_key] = agent_result[key]

            except Exception as e:
                logger.error("[Sequential] Agent '%s' failed: %s", agent_name, e)
                results.append({"agent": agent_name, "status": "failed", "error": str(e)})
                break

        return self.format_result(
            "completed",
            {"results": results, "shared_context": shared_context},
            f"顺序执行完成: {len(results)}/{len(self._agent_names)} Agent",
            details={"total": len(self._agent_names), "completed": len(results)},
        )
