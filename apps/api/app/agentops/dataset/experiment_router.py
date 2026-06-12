"""Experiment FastAPI 路由 — REST 接口。

Endpoints:
    POST   /api/v1/agentops/dataset/experiments          — 创建实验
    GET    /api/v1/agentops/dataset/experiments           — 实验列表
    GET    /api/v1/agentops/dataset/experiments/{id}      — 实验详情
    POST   /api/v1/agentops/dataset/experiments/{id}/run  — 执行实验
    GET    /api/v1/agentops/dataset/runs/{run_id}         — 运行详情
    GET    /api/v1/agentops/dataset/experiments/{id}/runs — 运行列表
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agentops.dataset.experiment_schemas import (
    ExperimentComparisonResponse,
    ExperimentCreate,
    ExperimentListResponse,
    ExperimentResponse,
    ExperimentRunCreate,
    ExperimentRunResponse,
    ExperimentRunSummaryResponse,
)
from app.agentops.dataset.experiment_service import ExperimentService
from app.agentops.evaluation.llm_judge import LLMJudgeFactory
from app.core.config import settings
from app.core.dependencies import get_current_user_id

router = APIRouter(prefix="/api/v1/agentops/dataset", tags=["agentops-experiment"])


def get_experiment_service() -> ExperimentService:
    judge = LLMJudgeFactory.from_settings(settings)
    return ExperimentService(judge_backend=judge)


@router.post("/experiments", response_model=ExperimentResponse, status_code=201)
async def create_experiment(
    req: ExperimentCreate,
    service: ExperimentService = Depends(get_experiment_service),
    user_id: str = Depends(get_current_user_id),
) -> ExperimentResponse:
    result = await service.create_experiment(req, created_by=user_id)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create experiment")
    return result


@router.get("/experiments", response_model=ExperimentListResponse)
async def list_experiments(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: ExperimentService = Depends(get_experiment_service),
) -> ExperimentListResponse:
    items, total = await service.list_experiments(status=status, limit=limit, offset=offset)
    return ExperimentListResponse(experiments=items, total=total, limit=limit, offset=offset)


@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: str,
    service: ExperimentService = Depends(get_experiment_service),
) -> ExperimentResponse:
    result = await service.get_experiment(experiment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.post("/experiments/{experiment_id}/run", response_model=ExperimentRunResponse, status_code=201)
async def run_experiment(
    experiment_id: str,
    run_req: ExperimentRunCreate | None = None,
    service: ExperimentService = Depends(get_experiment_service),
) -> ExperimentRunResponse:
    variant_idx = run_req.variant_index if run_req else 0
    result = await service.run_experiment(experiment_id, variant_index=variant_idx)
    if not result:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.get("/runs/{run_id}", response_model=ExperimentRunResponse)
async def get_run(
    run_id: str,
    service: ExperimentService = Depends(get_experiment_service),
) -> ExperimentRunResponse:
    result = await service.get_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@router.post("/experiments/{experiment_id}/compare", response_model=ExperimentComparisonResponse)
async def compare_variants(
    experiment_id: str,
    service: ExperimentService = Depends(get_experiment_service),
) -> ExperimentComparisonResponse:
    result = await service.compare_variants(experiment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.get("/experiments/{experiment_id}/runs", response_model=list[ExperimentRunSummaryResponse])
async def list_runs(
    experiment_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: ExperimentService = Depends(get_experiment_service),
) -> list[ExperimentRunSummaryResponse]:
    items, total = await service.list_runs(experiment_id, limit=limit, offset=offset)
    return items
