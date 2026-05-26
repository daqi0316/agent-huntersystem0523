# Anchored Summary

## Goal
Analyze existing `agent-huntersystem0523` codebase (backend + frontend), research Hermes Agent architecture, produce comprehensive gap analysis, and deliver PRD v2 grounded in actual codebase state.

## Constraints & Preferences
- FastAPI backend + Next.js 14 frontend, monorepo with Turborepo + pnpm
- Backend: async SQLAlchemy + Pydantic v2 schemas + custom Agent framework (6 patterns)
- Frontend: `'use client'`, shadcn/ui, Recharts, Zustand, direct fetch API
- Hermes Agent used as reference architecture for self-improving agents

## Progress
### Done
- **Backend (apps/api) deep analysis**: Documented all 6 Agent patterns (Pipeline with gate, Router, Aggregator with consensus, Orchestrator with DAG, GenEvalLoop, HumanLoop), AgentService (11 built-in tools), dynamic Skill system (weather + web_search), LLM dual-client (OMLX/vLLM), storage (PostgreSQL/Redis/Qdrant/Alembic), 20+ API route modules
- **Frontend (apps/web) deep analysis**: 12 pages (Dashboard/Jobs/Candidates/Screening/Interview/Reports/Knowledge/Settings/Agent Chat/Evaluation/Talent Profile/JD Generator), shadcn/ui components, Recharts charts, Zustand state, auth guard, ReAct chat UI with tool call visualization
- **Hermes Agent research**: Studied self-improving loop (experience → skill extraction → registry), FTS5 cross-session memory, multi-platform support, sub-agent budgets, MCP integration, progressive skill disclosure
- **Comparative analysis**: 9-dimension gap table comparing current system vs Hermes vs recruitment-specific needs
- **PRD v2 delivered**: Updated `AI_Recruitment_System_PRD.md` — now grounded in actual codebase analysis with explicit gap identification and phased evolution roadmap (4 phases: Infrastructure → Learning Loop → Assistant AI → Commercialization)

### In Progress
- (none)

### Blocked
- (none)

## Key Decisions
- PRD v2 format shifted from "design from scratch" to "acknowledge current state, plan evolution" — reflects actual codebase is 90%+ feature-complete
- Hermes-inspired features (cross-session memory, skill evolution, behavioral modeling) prioritized as Phase 2, not current rewrite
- Marketing features (multi-platform, sub-agent budgets) deprioritized — recruitment is web-first

## Next Steps
1. Review PRD v2 and decide which Phase to start executing
2. Recommended first step: close the candidate data flow loop (import → extract → screen → evaluate → interview)
3. Followed by: cross-session memory implementation (PostgreSQL FTS + session summarization)

## Critical Context
- This session was purely research + analysis + documentation, no code changes
- Existing PRD (`AI_Recruitment_System_PRD.md`) overwritten with v2 grounded in actual codebase analysis
- All 7 Agent patterns from the original PRD are already implemented in the codebase — no new patterns needed
- Key gap: no cross-session learning, no skill evolution, no behavioral modeling

## Relevant Files
- `AI_Recruitment_System_PRD.md` — Updated PRD v2.1 with codebase analysis and evolution roadmap
- `apps/api/app/agents/` — 6 Agent patterns + AgentService + Skill system
- `apps/api/app/api/` — 20+ route modules
- `apps/api/app/llm/` — OMLXClient + VLLMClient
- `apps/api/app/skills/` — Dynamic skill discovery (weather, web_search)
- `apps/web/app/` — 12 Next.js pages
- `.omo/anchor/anchor-summary.md` — This file
