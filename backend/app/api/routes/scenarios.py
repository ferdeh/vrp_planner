"""Scenario and route query routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import schemas
from app.repositories.scenario_repository import ScenarioRepository
from app.services.result_service import ResultService

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


@router.get("", response_model=schemas.ScenarioQueryResponse)
def list_scenarios(db: Session = Depends(get_db)) -> schemas.ScenarioQueryResponse:
    """List scenario history with dashboard summary."""

    return ScenarioRepository(db).list_scenarios()


@router.get("/{scenario_id}", response_model=schemas.ScenarioDetailResponse)
def get_scenario_detail(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> schemas.ScenarioDetailResponse:
    """Return scenario detail."""

    scenario = ScenarioRepository(db).get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return ResultService().build_detail_response(scenario)


@router.get("/{scenario_id}/routes", response_model=list[schemas.RouteDetailResponse])
def get_scenario_routes(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> list[schemas.RouteDetailResponse]:
    """Return route list for a scenario."""

    detail = get_scenario_detail(scenario_id, db)
    return detail.route_details


@router.get("/{scenario_id}/truck-summary", response_model=schemas.TruckSummaryResponse)
def get_truck_summary(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> schemas.TruckSummaryResponse:
    """Return truck composition summary."""

    detail = get_scenario_detail(scenario_id, db)
    return schemas.TruckSummaryResponse(
        scenario_id=detail.scenario_id,
        active_truck_count=detail.active_truck_count,
        active_truck_type_summary=detail.active_truck_type_summary,
    )


@router.delete("", response_model=schemas.DeleteScenariosResponse)
def delete_scenarios(
    payload: schemas.DeleteScenariosRequest,
    db: Session = Depends(get_db),
) -> schemas.DeleteScenariosResponse:
    """Delete selected scenarios and their dependent records."""

    deleted_count = ScenarioRepository(db).delete_scenarios(payload.scenario_ids)
    return schemas.DeleteScenariosResponse(deleted_count=deleted_count)
