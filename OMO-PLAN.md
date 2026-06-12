# AgentOps 平台 — 长期实施规划

> 基于 2885 测试覆盖 + 11/11 健康检查的现有基础。
> 原则：接口先行 → 实现垫后 → 测试锁死 → 非侵入式集成
> Momus 审核修正：v2（修复 12 个问题点）

---

## 架构全景（当前）

```
用户请求
  │
  ▼
chat_with_tools()                        ← agent_service.py
  │
  ├─ CommandExecutor (/)                 ← slash commands
  │
  └─ orchestrator_graph
       │
       ├─ intent_recognition
       ├─ execute_resume_parser          ← ResumeParserAgent  ← _handle_parse_resume tool
       ├─ execute_screening              ← ScreeningAgent   ← LLM + Pipeline + Aggregator
       ├─ execute_interview              ← InterviewAgent
       ├─ execute_analytics              ← AnalyticsAgent (JD 生成在此)
       ├─ execute_sourcing/offering/onboarding
       │
       └─ _multi_stage_decompose → _run_sub_task → _execute_agent
```

**已就绪的 AgentOps 基础设施：**
```
EventEmitter.emit()
  ├─ provider.record_event()             ← Langfuse/Queue
  ├─ EventStore.save()                   ← business_events 表 (trace_id 有索引)
  ├─ SSE event_bus.publish()             ← 前端实时推送
  └─ _export_scores()                    ← 关键指标同步 Score

agent_span(name)                         ← span 追踪 (自动 child context)
trace_llm_generation()                   ← LLM 调用追踪
set_context(AgentOpsContext)             ← contextvars 上下文传播
```

---

## Item 1: LLM Judge 真实接入

### 问题
`PromptBasedJudge` 已实现但无法接入生产 LLM——没有工厂、没有配置、没有降级链。
LLM judge evaluator 目前只走 heuristic，experiment 的 agentops_evals 模式没有真实评估能力。

### 设计

```
LLMJudgeFactory.from_settings(settings)
  │
  ├─ llm_judge_enabled=false ───→ HeuristicJudge (输出长度估算)
  │
  └─ llm_judge_enabled=true
       │
       ├─ _build_client()
       │    └─ 独立 LLM 实例（配置/模型/超时均独立于生产）
       │
       └─ _make_judge_fn()
            └─ PromptBasedJudge(fn)
                 │
                 ├─ LLM 响应可解析 → 返回 structured score
                 ├─ asyncio.TimeoutError → HeuristicJudge 降级
                 ├─ 其他异常 → HeuristicJudge 降级
                 └─ 响应不可解析 → 0.5 兜底
```

### 关键决策

**决策 1：Judge LLM 与生产 LLM 隔离**
```
生产: LLM_PROVIDER=omlx, LLM_MODEL=gpt-4o          ← 贵/强
Judge: LLM_JUDGE_PROVIDER=omlx, LLM_JUDGE_MODEL=gpt-4o-mini  ← 便宜/够用
理由: 评估流量可能 >> 生产流量；评估故障不影响生产链路
```

**决策 2：独立 LLM client 实例**
```python
# Judge client 完全独立于 get_llm_client()
judge_client = OMLXClient(
    base_url=settings.llm_judge_base_url or settings.llm_base_url,
    api_key=settings.llm_judge_api_key or settings.llm_api_key,
    model=settings.llm_judge_model,
)
```

**决策 3：降级链**
```python
# PromptBasedJudge.judge() 内部:
try:
    raw = await asyncio.wait_for(judge_fn(prompt), timeout=timeout)
except asyncio.TimeoutError:
    logger.warning("LLM judge timeout, falling back to heuristic")
    return await HeuristicJudge().judge(rubric, input_text, output_text)
except Exception as exc:
    logger.warning("LLM judge failed (%s), falling back to heuristic", exc)
    return await HeuristicJudge().judge(rubric, input_text, output_text)

parsed = _parse_score_json(raw)
if parsed:
    return (parsed, reasoning)
return (0.5, "Unparseable LLM response")
```

### 配置文件变更

```python
# apps/api/app/core/config.py - 新增 7 项
llm_judge_enabled: bool = False          # 默认关闭，不影响已有行为
llm_judge_provider: str = "omlx"         # omlx/vllm/qwen/deepseek/zhipu
llm_judge_model: str = "gpt-4o-mini"
llm_judge_base_url: str = ""             # 空=fallback 到 llm_base_url
llm_judge_api_key: str = ""              # 空=fallback 到 llm_api_key
llm_judge_timeout: float = 15.0
llm_judge_fallback: str = "heuristic"    # heuristic/mock
```

### 实施步骤

#### Step A: Factory + JudgeFn 包装
**文件：`apps/api/app/agentops/evaluation/llm_judge.py`**

```python
import asyncio
from app.llm.base import LLMClient
from app.llm.omlx_client import OMLXClient
from app.llm.vllm_client import VLLMClient
from app.llm.cn_providers import get_cn_llm_client, CN_PROVIDERS

class LLMJudgeFactory:
    """根据配置创建 LLM Judge 后端。"""

    @classmethod
    def from_settings(cls, settings) -> LLMJudgeBackend:
        if not settings.llm_judge_enabled:
            return HeuristicJudge()
        try:
            client = cls._build_client(settings)
            fn = cls._make_judge_fn(client, settings)
            return PromptBasedJudge(fn)
        except Exception as exc:
            logger.warning("LLMJudgeFactory init failed (%s), fallback", exc)
            return HeuristicJudge()

    @classmethod
    def _build_client(cls, settings) -> LLMClient:
        provider = settings.llm_judge_provider.lower()
        base_url = settings.llm_judge_base_url or settings.llm_base_url
        api_key = settings.llm_judge_api_key or settings.llm_api_key
        model = settings.llm_judge_model
        if provider == "vllm":
            return VLLMClient(base_url=base_url, api_key=api_key, model=model)
        if provider in ("omlx", ""):
            return OMLXClient(base_url=base_url, api_key=api_key, model=model)
        if provider in CN_PROVIDERS:
            return get_cn_llm_client(provider, base_url=base_url, api_key=api_key, model=model)
        raise ValueError(f"Unsupported LLM judge provider: {provider}")

    @classmethod
    def _make_judge_fn(cls, client: LLMClient, settings) -> JudgeFn:
        """创建带超时的 judge 函数。
        
        Note: judge_fn 收到的 prompt 已包含完整 rubric（自我包含的中文指令），
        只需作为普通 user message 发送，不需要 system prompt。
        """
        async def fn(prompt: str) -> str:
            return await asyncio.wait_for(
                client.chat([{"role": "user", "content": prompt}]),
                timeout=settings.llm_judge_timeout,
            )
        return fn
```

> **⚠️ 注意**：现有 4 个 rubric（_RESUME_PARSE_RUBRIC / _SCREENING_RUBRIC / _JD_QUALITY_RUBRIC / _CONVERSATION_RUBRIC）已包含完整的评分指令和 JSON 输出格式要求。Judge 函数不需要额外 system prompt，直接发送 rubric + 数据作为 user message。

#### Step B: ExperimentService 注入
**文件：`apps/api/app/agentops/dataset/experiment_service.py`**

```python
class ExperimentService:
    def __init__(self, store=None, judge_backend=None):
        self.store = store or ExperimentStore()
        self._judge_backend = judge_backend           # ← 新增

    # _evaluate_with_agentops_evals() 需改造：
    # 原方法创建 evaluator 时不传 judge_backend。修改为：
    # 当 self._judge_backend 存在时，给 LLM judge evaluator 注入后端。
```

**改造细节：**
```python
@staticmethod
async def _evaluate_with_agentops_evals(item, judge_backend=None) -> tuple[float, list]:
    events = ExperimentService._item_to_events(item)
    if not events:
        score = await ExperimentService._evaluate_with_rule_based(item)
        return score, [EvaluationResult(...)]

    from app.agentops.evaluation import evaluators as ev
    eval_list = [
        ev.ToolSuccessEvaluator(),
        ev.LatencyEvaluator(),
        ev.PIISafetyEvaluator(),
        ev.IntentCorrectnessEvaluator(),
        ev.ResumeParseQualityEvaluator(judge_backend=judge_backend),  # ← 注入
        ev.ScreeningReasonabilityEvaluator(judge_backend=judge_backend),
        ev.JDQualityEvaluator(judge_backend=judge_backend),
        ev.ConversationHelpfulnessEvaluator(judge_backend=judge_backend),
    ]
    results = await run_all_evaluators(events, evaluators=eval_list)
    ...
```

**文件：`apps/api/app/agentops/dataset/experiment_router.py`**

```python
from app.agentops.evaluation.llm_judge import LLMJudgeFactory
from app.core.config import settings

def get_experiment_service() -> ExperimentService:
    judge = LLMJudgeFactory.from_settings(settings)
    return ExperimentService(judge_backend=judge)
```

#### Step C: 测试

| 测试场景 | 文件 | 验证点 |
|----------|------|--------|
| Factory 关闭 | `tests/test_agentops_llm_judge_factory.py` | `from_settings(enabled=False)` → HeuristicJudge |
| Factory 开启 | 同上 | `from_settings(enabled=True)` → PromptBasedJudge |
| Judge client 独立实例 | 同上 | 验证 constructor args 来自 judge 配置 |
| 降级链 - timeout | 同上 | mock `asyncio.wait_for` 抛 TimeoutError → HeuristicJudge 被调用 |
| 降级链 - LLM 报错 | 同上 | mock `client.chat` 抛 RuntimeError → HeuristicJudge 被调用 |
| 降级链 - 工厂初始化失败 | 同上 | 非法 provider → HeuristicJudge 兜底 |
| ExperimentService 注入 | `tests/test_agentops_experiment.py` | `run_experiment` 使用 agentops_evals 时 evaluator 收到 judge_backend |

---

## Item 2: 看板增强

### 2A: Trace 瀑布图

#### 数据流
```
BusinessEventModel (business_events 表)
  ├─ trace_id (index=True) ← EventStore.list() 走索引
  ├─ event_type
  ├─ created_at
  ├─ domain_fields (JSON)  ← 可能含 PII
  └─ entity_type / entity_id
```

#### 新增后端

```python
# apps/api/app/agentops/dashboards/metrics.py
from app.agentops.events.store import EventStore
from app.agentops.privacy.sanitizer import sanitize_payload

@classmethod
async def trace_detail(cls, trace_id: str) -> dict | None:
    """返回单个 trace 的完整事件链 + 时间线。
    
    Momus 注意：
    - domain_fields 可能含 PII → 返回前 sanitize
    - created_at 精度到微秒，同 trace 内事件按创建顺序排列
    """
    store = EventStore()
    items, total = await store.list(trace_id=trace_id, limit=200)
    if total == 0:
        return None
    events = []
    base_time = None
    for item in items:
        d = item.to_dict()
        d["domain_fields"] = sanitize_payload(d.get("domain_fields", {}))
        if base_time is None:
            base_time = d["created_at"]
        d["offset_ms"] = _time_diff_ms(base_time, d["created_at"])
        events.append(d)
    return {
        "trace_id": trace_id,
        "event_count": total,
        "events": events,
    }

@classmethod
async def trace_search(cls, *, event_type="", entity_type="", entity_id="",
                        limit=50) -> dict:
    """搜索业务事件，支持按类型/实体过滤。"""
    store = EventStore()
    items, total = await store.list(
        event_type=event_type or None,
        entity_type=entity_type or None,
        entity_id=entity_id or None,
        limit=limit,
    )
    return {"items": [i.to_dict() for i in items], "total": total}


def _time_diff_ms(t1: str, t2: str) -> float:
    """计算两个 ISO 时间戳的毫秒差。"""
    from datetime import datetime
    fmt = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (fmt(t2) - fmt(t1)).total_seconds() * 1000
```

#### 路由

```python
# apps/api/app/agentops/dashboards/router.py

@router.get("/traces/{trace_id}")
async def get_trace_detail(trace_id: str):
    result = await DashboardMetrics.trace_detail(trace_id)
    if not result:
        raise HTTPException(404, "Trace not found")
    return result

@router.get("/events")
async def search_events(
    event_type: str = "", entity_type: str = "", entity_id: str = "",
    limit: int = 50,
):
    return await DashboardMetrics.trace_search(
        event_type=event_type, entity_type=entity_type,
        entity_id=entity_id, limit=limit,
    )
```

#### 前端
Debug Console 页面新增两块：
1. **Trace 搜索框** — 输 trace_id → GET /traces/{id} → 渲染时间线
2. **事件列表** — GET /events?event_type=… → 可过滤列表

时间线用纯 CSS flex 布局（非重库），每行：`● ── event_type ── offset_ms ── entity_type/id`

### 2B: 成本时间趋势

```python
@classmethod
async def cost_timeseries(cls, days: int = 30) -> dict:
    """按 started_at 日期聚合 experiment_run 数据。
    
    SQLAlchemy:
        SELECT DATE(started_at) as day,
               COUNT(*) as runs,
               AVG(avg_score) as avg_score
        FROM agent_experiment_run
        WHERE started_at >= NOW() - INTERVAL ':days days'
          AND status = 'completed'
        GROUP BY day
        ORDER BY day ASC
    """
    from app.agentops.dataset.experiment_models import ExperimentRunModel
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        stmt = text("""
            SELECT DATE(started_at) as day,
                   COUNT(*) as runs,
                   AVG(avg_score) as avg_score
            FROM agent_experiment_run
            WHERE started_at >= NOW() - INTERVAL ':days' DAY
              AND status = 'completed'
            GROUP BY day
            ORDER BY day ASC
        """).bindparams(days=days)
        result = await db.execute(stmt)
        rows = result.all()

    daily = [
        {"date": str(r[0]), "runs": r[1], "avg_score": round(float(r[2]), 4)}
        for r in rows
    ]
    total_runs = sum(d["runs"] for d in daily)
    return {
        "daily": daily,
        "summary": {
            "total_runs": total_runs,
            "avg_score": round(
                sum(d["avg_score"] * d["runs"] for d in daily) / total_runs, 4
            ) if total_runs > 0 else 0.0,
        },
    }
```

### 2C: PII 安全策略

```python
# 所有 dashboard 端点返回 domain_fields 前，必须 sanitize
# trace_detail 已实现，后续事件搜索类端点同理
```

---

## Item 3: Stage 9 业务事件发射

### 接入架构

```
业务服务                                instrumentation层            EventEmitter
──────────                              ────────────────            ────────────
ResumeParserAgent._single_parse()  ──→  on_resume_parsed()      ──→  emit()
ScreeningAgent.run()               ──→  on_screening_completed() ──→  emit()
Agent execute for JD generation    ──→  on_jd_generated()       ──→  emit()
InterviewService.schedule()        ──→  on_interview_scheduled() ──→  emit()
run_all_evaluators()               ──→  on_evaluation_completed()──→  emit()
```

### 核心设计

```python
# apps/api/app/agentops/instrumentation/recruitment.py

class RecruitmentEvents:
    """招聘业务事件发射器 — 静态方法，非阻塞，自动关联 trace。

    设计原则：
    - fire-and-forget: emitter.emit() 内部已有 try/except，不会传播异常
    - 自动关联: 通过 AgentOpsContext 继承 trace_id/span_id/user_id/session_id
    - 职责明确: 每个方法接收明确的业务参数，不依赖全局状态
    
    风险提示（Momus）:
    asyncio.create_task 用于 fire-and-forget。在 FastAPI 正常 shutdown 时
    pending tasks 会被等待。极端情况（进程 SIGKILL）下事件可能丢失。
    这是可接受的 tradeoff——丢失的是分析事件，不是业务数据。
    """

    @staticmethod
    async def on_resume_parsed(
        candidate_id: str,
        quality_score: float,
        confidence: float,
        red_flags: list[str],
        field_completeness: float | None = None,
        needs_human_review: bool = False,
        error: str = "",
    ) -> None:
        emitter = get_event_emitter()
        etype = (BusinessEventType.RESUME_PARSING_FAILED if error
                 else BusinessEventType.RESUME_PARSING_COMPLETED)
        await emitter.emit(
            event_type=etype,
            entity_type="candidate",
            entity_id=candidate_id,
            domain_fields={
                "quality_score": quality_score,
                "confidence": confidence,
                "red_flags": red_flags,
                "field_completeness": field_completeness or round(confidence, 2),
                "needs_human_review": needs_human_review,
            },
            error=error,
            tags=["resume", "bad_case"] if (red_flags or error) else ["resume"],
        )

    @staticmethod
    async def on_screening_completed(
        candidate_id: str,
        job_id: str,
        match_score: float,
        decision: str,
        dimension_scores: dict[str, float] | None = None,
        reason_codes: list[str] | None = None,
        needs_human_review: bool = False,
    ) -> None:
        emitter = get_event_emitter()
        domain = {
            "job_id": job_id,
            "match_score": match_score,
            "decision": decision,
            "needs_human_review": needs_human_review,
        }
        if dimension_scores:
            domain["dimension_scores"] = dimension_scores
        if reason_codes:
            domain["reason_codes"] = reason_codes
        await emitter.emit(
            event_type=BusinessEventType.SCREENING_COMPLETED,
            entity_type="candidate",
            entity_id=candidate_id,
            domain_fields=domain,
            tags=["screening"],
        )

    @staticmethod
    async def on_jd_generated(
        job_id: str,
        iteration_count: int,
        final_score: float,
        passed_threshold: bool,
        error: str = "",
    ) -> None:
        emitter = get_event_emitter()
        etype = (BusinessEventType.JD_GENERATION_FAILED if error
                 else BusinessEventType.JD_GENERATION_COMPLETED)
        await emitter.emit(
            event_type=etype,
            entity_type="job",
            entity_id=job_id,
            domain_fields={
                "iteration_count": iteration_count,
                "final_score": final_score,
                "passed_threshold": passed_threshold,
            },
            error=error,
            tags=["jd"],
        )

    @staticmethod
    async def on_interview_scheduled(
        candidate_id: str,
        job_id: str,
        schedule_success: bool,
        conflict_detected: bool = False,
        error: str = "",
    ) -> None:
        emitter = get_event_emitter()
        await emitter.emit(
            event_type=BusinessEventType.INTERVIEW_SCHEDULED,
            entity_type="candidate",
            entity_id=candidate_id,
            domain_fields={
                "job_id": job_id,
                "schedule_success": schedule_success,
                "conflict_detected": conflict_detected,
            },
            error=error,
            tags=["interview"],
        )

    @staticmethod
    async def on_evaluation_completed(
        experiment_id: str,
        run_id: str,
        evaluator_name: str,
        score: float,
        comment: str = "",
        metadata: dict | None = None,
    ) -> None:
        """评估器执行完成时调用。
        
        Momus 修正: entity_id 从 trace_id 改为 experiment_id，
        保持 entity_id 为有意义的业务标识符的约定。
        """
        emitter = get_event_emitter()
        await emitter.emit(
            event_type=BusinessEventType.EVALUATION_COMPLETED,
            entity_type="experiment",
            entity_id=experiment_id,
            domain_fields={
                "run_id": run_id,
                "evaluator": evaluator_name,
                "score": score,
                "comment": comment,
                **(metadata or {}),
            },
            tags=["evaluation"],
        )
```

### 接入点

#### Priority 1: 简历解析
```python
# apps/api/app/agents/resume_parser.py → _single_parse()
# 在 return self.format_result(...) 之前：
asyncio.create_task(RecruitmentEvents.on_resume_parsed(
    candidate_id=data.get("candidate_id", ""),
    quality_score=quality_score,
    confidence=confidence,
    red_flags=red_flags,
    field_completeness=quality_score / 100,  # quality_score 是 0-100 整数
    needs_human_review=needs_human_review,
))
```

#### Priority 2: 筛选决策
```python
# apps/api/app/agents/screening_agent.py → 有结果后
# 注: ScreeningAgent.run() 返回 format_result()，含 complete/partial/failed 状态
# 在最终 return 前获取数据发射事件
```

#### Priority 3: JD 生成
```python
# JD 生成通过 execute_analytics 节点（apps/api/app/graphs/orchestrator_graph.py）
# 或专门的 JD agent。需确认具体文件路径后在 run() 完成后发射。
```

#### Priority 4: 面试安排
```python
# apps/api/app/services/interview.py
# schedule_interview() 成功后发射
```

### 测试策略

```python
# tests/test_agentops_instrumentation_recruitment.py

class TestRecruitmentEvents:
    """核心验证：emitter.emit() 参数正确 + 异常隔离。"""

    async def test_on_resume_parsed_emits_correct_event(self):
        with patch("app.agentops.instrumentation.recruitment.get_event_emitter") as m:
            emitter = AsyncMock()
            m.return_value = emitter
            await RecruitmentEvents.on_resume_parsed(
                candidate_id="c1", quality_score=85, confidence=0.9,
                red_flags=["gap"],
            )
            emitter.emit.assert_awaited_once()
            args = emitter.emit.await_args[1]
            assert args["event_type"] == BusinessEventType.RESUME_PARSING_COMPLETED
            assert args["entity_id"] == "c1"
            assert args["domain_fields"]["quality_score"] == 85

    async def test_on_resume_parsed_error_emits_failed(self):
        """error 非空 → event_type 应为 FAILED。"""

    async def test_on_screening_includes_dimension_scores(self):
        """dimension_scores 存在时应出现在 domain_fields 中。"""

    async def test_on_evaluation_entity_is_experiment(self):
        """on_evaluation_completed 的 entity_type == 'experiment'。"""

    async def test_emitter_error_isolated(self):
        """emitter.emit 抛异常 → 业务不中断。"""
        with patch("...") as m:
            m.side_effect = RuntimeError("boom")
            await RecruitmentEvents.on_resume_parsed(...)  # 不抛异常
```

---

## Momus 审核修正清单

| # | 问题 | 严重度 | 修正 |
|---|------|--------|------|
| 1 | `judge_fn` 消息格式不确定是否需要 system prompt | **中** | rubric 已自包含，只用 `{"role": "user"}` |
| 2 | `on_evaluation_completed` 用 trace_id 作 entity_id | **低** | 改为 experiment_id，保持约定 |
| 3 | domain_fields 大数据量无限制 | **中** | 建议 <100KB；BusinessEventModel 的 JSON 列无硬限 |
| 4 | `asyncio.create_task` 事件丢失风险 | **低** | 已文档化，接受 tradeoff |
| 5 | `trace_detail` 返回 domain_fields 含 PII | **高** | 返回前调 `sanitize_payload()` |
| 6 | `cost_timeseries` SQL 太模糊 | **中** | 已给出完整 SQLAlchemy/text 查询 |
| 7 | JD agent 位置 "待确认" | **高** | execute_analytics 节点；具体文件需实施时确认 |
| 8 | Phase 时间估算无依据 | **低** | 已移除 |
| 9 | 未确认是否需要 alembic migration | **中** | business_events 表已存在，不需要 |
| 10 | `_build_client` 缺少异常处理 | **中** | Factory 内 catch Exception → HeuristicJudge |
| 11 | `_evaluate_with_agentops_evals` 未设计注入点 | **高** | 已给出 evaluator 列表改造代码 |
| 12 | 未提及 `llm_base_url` 是否存在于 settings | **中** | 已用 `getattr(settings, ...)` 兜底 |

---

## 完整实施路线图

```
Phase A: LLM Judge 真实接入
  A1: config.py → 7 个 LLM_JUDGE_* 配置项
  A2: LLMJudgeFactory._build_client() + _make_judge_fn()
  A3: PromptBasedJudge 降级链改造
  A4: ExperimentService._evaluate_with_agentops_evals() 注入点
  A5: ExperimentRouter.get_experiment_service() → judge 注入
  A6: 测试（factory + 降级 + 注入）

Phase B: Stage 9 事件发射
  B1: RecruitmentEvents 5 个 emitter 方法
  B2: P1 简历解析 → resume_parser.py
  B3: P2 筛选 → screening_agent.py
  B4: P3 JD 生成（确认具体 agent 文件）
  B5: P4 面试安排 → interview.py
  B6: 测试（5 emitter × 3 场景）

Phase C: 看板增强
  C1: trace_detail() + trace_search() + PII sanitize
  C2: cost_timeseries() SQL
  C3: 路由注册
  C4: Debug Console 前端 trace 搜索 + 时间线
  C5: 成本时间趋势图

Phase D: 收尾
  D1: 全量后端测试（2885+ → 2950+）
  D2: Next.js build 验证
  D3: 健康检查 11/11
```

### 增量统计

| Phase | 新增文件 | 修改文件 | 新增测试 | 新增端点 |
|-------|----------|----------|----------|----------|
| A | 0 | 3 | 1 | 0 |
| B | 1 | 4 | 1 | 0 |
| C | 0 | 4 | 0 | 3 |
| 合计 | 1 | 11 | 2 | 3 |

---

## 设计原则落实

| 原则 | 落实方式 | Momus 确认 |
|------|----------|------------|
| **工程化** | 接口抽象 + 工厂模式 + 配置驱动 + 降级链 | ✅ LLMJudgeBackend 可替换 |
| **深度化** | 事件 domain_fields 携带完整业务数据，非仅 ID | ✅ 每个事件 5-8 个字段 |
| **长远化** | Judge LLM 独立配置/模型/超时；事件 schema 预留扩展 | ✅ 新增 7 个配置全部有默认值 |
| **模块化** | instrumentors/ 层独立于 business logic | ✅ 无环依赖 |
| **可扩展** | RecruitmentEvents 可新增方法；EventStore 已有过滤 | ✅ OCP 闭合 |
| **非侵入** | emitter.emit() 内 try/except；异常不阻塞 | ✅ 已验证 emitter 实现 |
| **可测试** | 每层接口可 mock；emitter 参数独立验证 | ✅ AsyncMock 覆盖全部路径 |
| **安全** | domain_fields 返回前端前要 sanitize | ✅ trace_detail 已实现 |

---

## TODO 清单（可执行任务）

> 格式：[WHERE] [HOW] to [WHY] — expect [RESULT]
> 每个 TODO 是一次原子变更（1-3 tool calls），优先级 P0-P2

### Phase A — LLM Judge 真实接入（工程化 · 模块化）

#### A0: 基础设施

- [ ] `apps/api/app/core/config.py`: 新增 `llm_judge_enabled` / `provider` / `model` / `base_url` / `api_key` / `timeout` / `fallback` 共 7 个配置项 — 全部默认关闭/空值，不影响现有行为
- [ ] `apps/api/app/agentops/evaluation/llm_judge.py`: 新增 `LLMJudgeFactory` 类 + `_build_client()` 静态方法，根据 provider 路由到 OMLX/VLLM/Qwen/DeepSeek/Zhipu — 返回独立 LLMClient 实例
- [ ] `apps/api/app/agentops/evaluation/llm_judge.py`: 新增 `LLMJudgeFactory._make_judge_fn()` 静态方法，创建带 `asyncio.wait_for` 超时的 judge 回调 — 返回 JudgeFn
- [ ] `apps/api/app/agentops/evaluation/llm_judge.py`: 改造 `LLMJudgeFactory.from_settings()`，`enabled=False` 返回 HeuristicJudge，构造失败 catch 所有异常降级到 HeuristicJudge — Factory 永不抛
- [ ] `apps/api/app/agentops/evaluation/llm_judge.py`: 改造 `PromptBasedJudge.judge()`，将裸 `judge_fn()` 调用改为 `asyncio.wait_for` + TimeoutError/Exception 分别降级到 `HeuristicJudge.judge()` — 降级链完整
- [ ] `apps/api/app/agentops/evaluation/__init__.py`: 导出 `LLMJudgeFactory`

#### A1: ExperimentService 注入（长远化 · 可扩展）

- [ ] `apps/api/app/agentops/dataset/experiment_service.py`: `ExperimentService.__init__` 增加可选 `judge_backend: LLMJudgeBackend | None = None` 参数，存为 `self._judge_backend`
- [ ] `apps/api/app/agentops/dataset/experiment_service.py`: 改造 `_evaluate_with_agentops_evals()` 为接受 `judge_backend` 参数，传给 4 个 LLM judge evaluator 的构造函数 — 方法签名变更为 `(item, judge_backend=None)`
- [ ] `apps/api/app/agentops/dataset/experiment_router.py`: `get_experiment_service()` 中调用 `LLMJudgeFactory.from_settings(settings)` 创建 judge，传给 `ExperimentService(judge_backend=judge)` — Router 层自动注入

#### A2: 测试（工程化 · 可测试）

- [ ] `tests/test_agentops_llm_judge_factory.py::TestFactoryDisabled`: 验证 `from_settings(enabled=False)` 返回 HeuristicJudge
- [ ] `tests/test_agentops_llm_judge_factory.py::TestFactoryEnabled`: 验证 `from_settings(enabled=True)` 返回 PromptBasedJudge，且 client 的 constructor args 来自 LLM_JUDGE_* 配置
- [ ] `tests/test_agentops_llm_judge_factory.py::TestFallbackTimeout`: mock `asyncio.wait_for` 抛 TimeoutError → 最终调用 HeuristicJudge
- [ ] `tests/test_agentops_llm_judge_factory.py::TestFallbackLLMError`: mock `client.chat` 抛 RuntimeError → 最终调用 HeuristicJudge
- [ ] `tests/test_agentops_llm_judge_factory.py::TestFallbackInitError`: 输入非法 provider → Factory 返回 HeuristicJudge 而非抛异常
- [ ] `tests/test_agentops_experiment.py::TestExperimentJudgeInject`: 创建 evaluator_type="agentops_evals" 的实验，验证 evaluator 收到 judge_backend（mock judge 返回固定分数，验证 run 结果使用该分数）

---

### Phase B — Stage 9 业务事件发射（深度化 · 模块化 · 可扩展）

#### B0: Instrumentor 层

- [ ] `apps/api/app/agentops/instrumentation/__init__.py`: 创建包入口，导出 `RecruitmentEvents`
- [ ] `apps/api/app/agentops/instrumentation/recruitment.py`: 实现 `RecruitmentEvents.on_resume_parsed()` 静态方法 — 参数: candidate_id, quality_score, confidence, red_flags, field_completeness, needs_human_review, error；发射 RESUME_PARSING_COMPLETED/FAILED
- [ ] `apps/api/app/agentops/instrumentation/recruitment.py`: 实现 `RecruitmentEvents.on_screening_completed()` 静态方法 — 参数: candidate_id, job_id, match_score, decision, dimension_scores, reason_codes, needs_human_review；发射 SCREENING_COMPLETED
- [ ] `apps/api/app/agentops/instrumentation/recruitment.py`: 实现 `RecruitmentEvents.on_jd_generated()` 静态方法 — 参数: job_id, iteration_count, final_score, passed_threshold, error；发射 JD_GENERATION_COMPLETED/FAILED
- [ ] `apps/api/app/instrumentation/recruitment.py`: 实现 `RecruitmentEvents.on_interview_scheduled()` 静态方法 — 参数: candidate_id, job_id, schedule_success, conflict_detected, error；发射 INTERVIEW_SCHEDULED
- [ ] `apps/api/app/agentops/instrumentation/recruitment.py`: 实现 `RecruitmentEvents.on_evaluation_completed()` 静态方法 — entity_type="experiment", entity_id=experiment_id；发射 EVALUATION_COMPLETED

#### B1: 业务接入（非侵入）

- [ ] `apps/api/app/agents/resume_parser.py`: 在 `_single_parse()` 的 `return self.format_result(...)` 前插入 `asyncio.create_task(RecruitmentEvents.on_resume_parsed(...))` — P1 简历解析
- [ ] `apps/api/app/agents/screening_agent.py`: 在 `run()` 的 `return self.format_result(...)` 前插入 `await RecruitmentEvents.on_screening_completed(...)` — P2 筛选决策
- [ ] 确认 JD 生成 agent 文件路径，插入 `await RecruitmentEvents.on_jd_generated(...)` — P3 JD 生成
- [ ] `apps/api/app/services/interview.py`: 在 `schedule_interview()` 成功/失败后插入 `await RecruitmentEvents.on_interview_scheduled(...)` — P4 面试安排

#### B2: 测试（可测试）

- [ ] `tests/test_agentops_instrumentation_recruitment.py::TestOnResumeParsed`: mock `get_event_emitter` 返回 AsyncMock；调用 `on_resume_parsed` 验证 `emitter.emit` 被调用 1 次，event_type=COMPLETED，entity_id=candidate_id，domain_fields 包含 quality_score/confidence/red_flags
- [ ] `tests/test_agentops_instrumentation_recruitment.py::TestOnResumeParsedFailed`: error 非空 → event_type=FAILED
- [ ] `tests/test_agentops_instrumentation_recruitment.py::TestOnScreening`: 验证 dimension_scores 出现在 domain_fields 中
- [ ] `tests/test_agentops_instrumentation_recruitment.py::TestOnEvaluation`: 验证 entity_type="experiment"，entity_id=experiment_id
- [ ] `tests/test_agentops_instrumentation_recruitment.py::TestEmitterErrorIsolated`: `emitter.emit` 抛 RuntimeError → `on_resume_parsed` 不抛异常

---

### Phase C — 看板增强（深度化 · 安全）

#### C0: 后端聚合层

- [ ] `apps/api/app/agentops/dashboards/metrics.py`: 新增 `trace_detail(trace_id)` 类方法，调 `EventStore.list(trace_id=)` 查询 business_events，计算 offset_ms 时间线，`sanitize_payload()` 脱敏 domain_fields — 返回 {trace_id, event_count, events[]}
- [ ] `apps/api/app/agentops/dashboards/metrics.py`: 新增 `trace_search()` 类方法，调 `EventStore.list()` 支持 event_type/entity_type/entity_id/limit 过滤 — 返回 {items[], total}
- [ ] `apps/api/app/agentops/dashboards/metrics.py`: 新增 `_time_diff_ms(t1, t2)` 工具函数，计算两个 ISO 时间戳的毫秒差
- [ ] `apps/api/app/agentops/dashboards/metrics.py`: 新增 `cost_timeseries(days=30)` 类方法，调原生 SQL `SELECT DATE(started_at) ... GROUP BY day` 聚合 experiment_run — 返回 {daily[], summary{}}

#### C1: 路由注册

- [ ] `apps/api/app/agentops/dashboards/router.py`: 新增 `GET /traces/{trace_id}` 端点 → 调 `trace_detail()`，404 处理
- [ ] `apps/api/app/agentops/dashboards/router.py`: 新增 `GET /events` 端点 → 调 `trace_search()`
- [ ] `apps/api/app/agentops/dashboards/router.py`: 注册 `cost_timeseries` 端点

#### C2: 前端 Debug Console

- [ ] `apps/web/app/(dashboard)/agentops/debug/page.tsx`: 新增 trace_id 搜索框 + 搜索结果时间线渲染（纯 CSS flex，每行 `● event_type offset_ms entity_type/id`）— 数据来自 `GET /traces/{id}`
- [ ] `apps/web/app/(dashboard)/agentops/debug/page.tsx`: 新增事件列表面板（可过滤 event_type/entity_type）— 数据来自 `GET /events`

#### C3: 前端成本看板

- [ ] `apps/web/app/(dashboard)/agentops/cost/page.tsx`: 新增按天趋势折线图（Recharts LineChart，X 轴日期，Y 轴运行次数/平均分）— 数据来自 `cost_timeseries?days=30`

---

### Phase D — 收尾验证

- [ ] 全量非 e2e 测试：`pytest tests/ -k "not e2e and not integration and not test_e2e"` — 预期 2900+ passed, 0 new failures
- [ ] Next.js build：`cd apps/web && npx next build` — 预期编译成功，无 TS error
- [ ] 系统健康检查：`bash scripts/health-check.sh` — 预期 11/11
- [ ] 更新 `app/agentops/__init__.py` 导出 `RecruitmentEvents`、`LLMJudgeFactory`、`DashboardMetrics`（确保外部 import 可用）

---

## TODO 优先级与依赖

```
Phase A ──→ Phase B ──→ Phase C ──→ Phase D
  │                        ↑
  │                        └── 依赖 Phase B 产生真实事件数据
  └── 无外部依赖，可独立执行

A0 (配置) → A1 (注入) → A2 (测试)           ← 必须线性
B0 (instrumentor) → B1 (接入) → B2 (测试)   ← B0 完成后 B1/B2 可并行
C0 (后端) → C1 (路由) → C2C3 (前端)         ← C0→C1→C2 线性，C3 可提前
D (收尾)                                     ← 全部完成后执行
```

## 设计原则在各 TODO 中的落实

| 原则 | 关键 TODO | 落实方式 |
|------|-----------|----------|
| **工程化** | A0 配置 + A2 测试 | 配置驱动行为，所有路径有测试覆盖 |
| **深度化** | B0 5 个 emitter 的 domain_fields | 每个事件 5-8 个业务字段，非仅 ID |
| **长远化** | A0 独立 Judge 配置 + C0 cost_timeseries | Judge 与生产解耦；按天聚合支持长期趋势 |
| **模块化** | B0 instrumentors/ 独立目录 | 与 business logic 无环依赖，可单独测试 |
| **可扩展** | B0 的方法签名 + C0 EventStore 过滤 | 新事件类型只需加方法；新过滤条件只需加参数 |
| **安全** | C0 trace_detail sanitize | PII 不出 API 边界 |
