"""Optimization routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import schemas
from app.repositories.scenario_repository import ScenarioRepository
from app.services.optimization_service import OptimizationService
from app.services.result_service import ResultService

router = APIRouter(prefix="/api/v1", tags=["optimization"])


@router.post("/optimize", response_model=schemas.OptimizationResultResponse)
def optimize_route(
    payload: schemas.OptimizationRequest,
    db: Session = Depends(get_db),
) -> schemas.OptimizationResultResponse:
    """Run synchronous dispatch optimization."""

    return OptimizationService(db).optimize(payload)


@router.get("/optimize/{scenario_id}", response_model=schemas.ScenarioDetailResponse)
def get_optimization_result(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> schemas.ScenarioDetailResponse:
    """Return detail of a previously optimized scenario."""

    scenario = ScenarioRepository(db).get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return ResultService().build_detail_response(scenario)

