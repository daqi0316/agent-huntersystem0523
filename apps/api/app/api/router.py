from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.agent import router as agent_router
from app.api.pipeline import router as pipeline_router
from app.api.router_route import router as router_route
from app.api.parallel import router as parallel_router
from app.api.orchestrator import router as orchestrator_router
from app.api.loop import router as loop_router
from app.api.human_loop import router as human_loop_router
from app.api.mcp_servers import router as mcp_servers_router
from app.api.tools import router as tools_router
from app.api.retrieval import router as retrieval_router
from app.api.knowledge import router as knowledge_router
from app.api.memory import router as memory_router
from app.api.candidates import router as candidates_router
from app.api.jobs import router as jobs_router
from app.api.dashboard import router as dashboard_router
from app.api.applications import router as applications_router
from app.api.settings import router as settings_router
from app.api.interviews import router as interviews_router
from app.api.evaluations import router as evaluations_router
from app.api.dashboard_reports import router as dashboard_reports_router
from app.api.resume import router as resume_router
from app.api.summaries import router as summaries_router
from app.api.screening import router as screening_router
from app.api.conversation import router as conversation_router
from app.api.recommendations import router as recommendations_router
from app.api.operations import router as operations_router
from app.api.audit import router as audit_router
from app.api.tasks import router as tasks_router

api_router = APIRouter()

# 认证
api_router.include_router(resume_router, prefix="/resume", tags=["Resume"])
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])

# 图1: 单Agent
api_router.include_router(agent_router, prefix="/agent", tags=["Agent"])

# 图2: 流水线
api_router.include_router(pipeline_router, prefix="/pipeline", tags=["Pipeline"])

# 图3: Router
api_router.include_router(router_route, prefix="/router", tags=["Router"])

# 图4: Aggregator
api_router.include_router(parallel_router, prefix="/parallel", tags=["Parallel"])

# 图5: Orchestrator
api_router.include_router(orchestrator_router, prefix="/orchestrator", tags=["Orchestrator"])

# 图6: Gen-Eval
api_router.include_router(loop_router, prefix="/loop", tags=["Loop"])

# 图7: Human-in-Loop
api_router.include_router(human_loop_router, prefix="/human-loop", tags=["Human Loop"])

# MCP Server management
api_router.include_router(mcp_servers_router, prefix="/mcp", tags=["MCP"])

# MCP Tools
api_router.include_router(tools_router, prefix="/tools", tags=["Tools"])

# Vector retrieval
api_router.include_router(retrieval_router, prefix="/retrieval", tags=["Retrieval"])

# Knowledge Base (RAG)
api_router.include_router(knowledge_router, prefix="/knowledge", tags=["Knowledge"])

# Memory
api_router.include_router(memory_router, prefix="/memory", tags=["Memory"])

# Candidates CRUD
api_router.include_router(candidates_router, prefix="/candidates", tags=["Candidates"])

# Jobs CRUD
api_router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])

# Dashboard Stats
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])

# Applications CRUD
api_router.include_router(applications_router, prefix="/applications", tags=["Applications"])

# Settings
api_router.include_router(settings_router, prefix="/settings", tags=["Settings"])

# Interviews CRUD
api_router.include_router(interviews_router, prefix="/interviews", tags=["Interviews"])

# Evaluations
api_router.include_router(evaluations_router, prefix="/evaluations", tags=["Evaluations"])

# Cross-session memory summaries
api_router.include_router(summaries_router, prefix="/summaries", tags=["Summaries"])

# Dashboard Reports (extended)
api_router.include_router(dashboard_reports_router, prefix="/dashboard", tags=["Dashboard"])

api_router.include_router(screening_router, prefix="/screen", tags=["Screening"])

# Conversation & Memory (multi-turn)
api_router.include_router(conversation_router, prefix="/conversation", tags=["Conversation"])

# Proactive Recommendations
api_router.include_router(recommendations_router, prefix="/recommendations", tags=["Recommendations"])

api_router.include_router(operations_router, prefix="/operations", tags=["Operations"])
api_router.include_router(audit_router, prefix="/audit", tags=["Audit"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
