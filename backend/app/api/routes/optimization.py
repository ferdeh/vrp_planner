"""Optimization routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import schemas
from app.repositories.scenario_repository import ScenarioRepository
from app.services.optimization_service import OptimizationService
from app.services.optimization_worker import optimization_worker
from app.services.result_service import ResultService

router = APIRouter(prefix="/api/v1", tags=["optimization"])


@router.post(
    "/optimize",
    response_model=schemas.OptimizationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def optimize_route(
    payload: schemas.OptimizationRequest,
    db: Session = Depends(get_db),
) -> schemas.OptimizationJobResponse:
    """Queue dispatch optimization in the background."""

    job, prepared_payload = OptimizationService(db).create_job(payload)
    optimization_worker.submit(job.scenario_id, prepared_payload)
    return job


@router.get("/optimize/{scenario_id}", response_model=schemas.ScenarioDetailResponse)
def get_optimization_result(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> schemas.ScenarioDetailResponse:
    """Return detail of a previously optimized scenario."""

    scenario = ScenarioRepository(db).get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    if scenario.result is None and scenario.status == "processing":
        raise HTTPException(status_code=409, detail="Scenario is still processing.")
    return ResultService().build_detail_response(scenario)
