# Phase T Findings: MCP Tool System + ResumeParsingAgent

**Date**: 2026-06-01
**Phase**: T (MCP Tool System + ResumeParsingAgent)
**Branch**: main
**Status**: T.1–T.7 complete (verification only, no code added); T.8 deferred

---

## 1. Discovery: Phase T Was Already Implemented

Unlike Phase S which required fresh code, Phase T was discovered to be **fully implemented** during Phase R's atomic commits (commit `692a96b` feat(agents) + `7c5d7ea` feat(models+services+tools+skills) + `2c29b43` test).

The `consolidated-next-plan.md` listed T.1–T.8 as work to do, but investigation on 2026-06-01 found all 7 implementation items already present and tested.

---

## 2. T.1–T.7 Verification Matrix

| # | Task | Plan File | Status | Evidence |
|---|---|---|---|---|
| T.1 | 精简 Prompt-H 到 80 行 | `app/agents/prompts/resume_parser.md` | ✅ DONE | `resumeParser.md` exists, 38 lines (well under 80) |
| T.2 | `ResumeParsingAgent` 7-step | `app/agents/resume_parser.py` | ✅ DONE | 151 lines, all 7 steps: validate→parse→confidence→quality→risk→dedup→output |
| T.3 | RouterAgent 注册 `resume_parser` | `app/agents/router_agent.py` | ✅ DONE | Line 21: `"resume_parser"` in intent list; Line 37: 7 keyword mappings (中文+EN) |
| T.4 | 迁移 screening `_BUILTIN_TOOLS` | `app/services/agent_service.py` | ✅ DONE | Lines 20-21: `from app.tools import all_tools, all_handlers`; `app/tools/screening.py` (87 lines) |
| T.5 | 迁移 interview `_BUILTIN_TOOLS` | 同 | ✅ DONE | `app/tools/interview.py` (51 lines); `all_builtin_tools()` aggregator |
| T.6 | `tests/test_tools/` 单测 | `apps/api/tests/test_tools/` | ✅ DONE | 3 test files: test_resume_parser.py (115L, 11 tests), test_interview.py, test_screening.py |
| T.7 | `tests/test_resume_parser_agent.py` | 同 | ✅ DONE | 104 lines, 8 tests covering all 3 actions (single/batch/get_profile) |
| T.8 | E2E 上传→解析→评估 | (none) | ⏸ DEFERRED | Requires dev server stack (OMLX:8000, vLLM:8001, API:8888) |

---

## 3. Test Results (Verification Run)

```
$ uv run --no-sync python -m pytest tests/test_tools/ tests/test_resume_parser_agent.py -q
.........................                                                [100%]
25 passed, 1 warning in 0.03s
```

| File | Tests | Status |
|---|---|---|
| `tests/test_tools/test_resume_parser.py` | 11 | ✅ |
| `tests/test_tools/test_interview.py` | (counted in 25) | ✅ |
| `tests/test_tools/test_screening.py` | (counted in 25) | ✅ |
| `tests/test_resume_parser_agent.py` | 8 | ✅ |
| **Total** | **25** | **100% pass** |

---

## 4. Architecture Verification

### Tool Definition (single source of truth)
```python
# app/tools/__init__.py (79 lines)
- discover_tools() — scans app/tools/ submodules
- discover_handlers() — returns {tool_name: async callable}
- all_tools() — OpenAI function-calling schema
- all_handlers() — aggregated handler map
```

### Agent Layer (no tool definitions, only orchestration)
```python
# app/agents/resume_parser.py (151 lines)
class ResumeParserAgent(BaseAgent):
    output_keys = ["candidate_id", "parsed_data", "quality_score"]
    async def run(self, input_data): ...
    async def _single_parse():  # 7-step workflow
    async def _batch_parse():   # batch action
    async def _get_profile():   # get_profile action
```

This matches the **Momus 修正原则** in `resume-parser-mcp-plan.md`:
- ✅ 工具定义一次（app/tools/）
- ✅ Agent 不定义工具，只编排工作流
- ✅ LLM 只在 parse + 评估介入
- ✅ 7-step 工作流用代码实现，非 LLM 循环

### Router Integration
```python
# app/agents/router_agent.py:21
"resume_parser",  # 11 total intents

# app/agents/router_agent.py:37
(["解析简历", "解析", "简历解析", "parse resume", "提取简历", "简历提取", "parse_resume"], "resume_parser"),
```

Chinese + English keyword detection: 7 phrases route to `resume_parser` agent.

---

## 5. T.8 E2E — Why Deferred

The plan's T.8 deliverable is "上传简历 → 解析 → 评估 跑通" (upload → parse → evaluate E2E flow). This requires:

1. **OMLX server** on port 8000 (chat/embed completions)
2. **vLLM server** on port 8001 (alternative LLM)
3. **API server** on port 8888 (FastAPI + LangGraph)
4. **Frontend** upload UI (Next.js on 3000)
5. **PostgreSQL + Redis + Qdrant + MinIO** via docker-compose

Per `handoff-20260523.md`, the dev stack runs via `make dev` or `docker-compose up`. None of these are available in this CLI environment. The T.8 work belongs to a Playwright E2E pass against a real dev deployment.

**Mitigation**: U.10 (E2E 回归 + 覆盖率守门) will cover T.8 as part of Phase U's production-readiness work. Playwright tests can be authored without running them in this session.

---

## 6. Decisions Surfaced by T Verification

### A. Phase T is a verification phase, not implementation
The plan's T.1–T.7 sub-tasks were all completed during Phase R's atomic commits. This phase therefore serves as a **smoke test** for those commits rather than new work.

### B. S.6 + T share `app/tools/resume_parser.py` already
The S phase's `app/graphs/resume_parser_graph.py` (LangGraph state machine) and T phase's `app/agents/resume_parser.py` (Python agent orchestration) coexist. The agent wraps the tool handlers; the graph provides checkpointed state. Both call the same `CandidateService` + `resume_extractor` underneath.

### C. No `_BUILTIN_TOOLS` literal in `agent_service.py`
The plan said "迁移 _BUILTIN_TOOLS screening 部分" — but `agent_service.py:20-21` already imports `from app.tools import all_tools, all_handlers as all_builtin_tools, all_builtin_handlers`. The local `_BUILTIN_TOOLS` constant at line 55 is `all_builtin_tools() + _BUILTIN_INSTALL_TOOLS` — a small composition that is *expected* to live in agent_service. The "migration" is complete; what's left is the composition glue, not a separate registry.

---

## 7. T Phase → U Phase Handoff

Phase U prerequisites (from `consolidated-next-plan.md`):
- ✅ OperationLog model (created in R's feat-models)
- ✅ Approval model (created in R's feat-models)
- ✅ operation_stats model (created in R's feat-models)
- ✅ MCP + Tool framework (Phase T)
- ✅ Agent registry (Phase R)

**Ready for Phase U**: Operations + Observability + Production ready.

U.1 (OperationLog `error_category`/`immutable`/`superseded_by`) is the natural first step.
