"""Scenario and route query routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import schemas
from app.repositories.scenario_repository import ScenarioRepository
from app.services.result_service import ResultService
from app.services.scenario_analysis_service import ScenarioAnalysisService
from app.services.scenario_analysis_worker import scenario_analysis_worker

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


@router.get("", response_model=schemas.ScenarioQueryResponse)
def list_scenarios(db: Session = Depends(get_db)) -> schemas.ScenarioQueryResponse:
    """List scenario history with dashboard summary."""

    return ScenarioRepository(db).list_scenarios()


@router.get("/analysis/jobs", response_model=schemas.ScenarioAnalysisOverviewResponse)
def list_all_scenario_analysis_jobs(
    db: Session = Depends(get_db),
) -> schemas.ScenarioAnalysisOverviewResponse:
    """List scenario analysis jobs across all scenarios."""

    return ScenarioAnalysisService(db).list_all_analysis_jobs()


@router.get("/{scenario_id}", response_model=schemas.ScenarioDetailResponse)
def get_scenario_detail(
    scenario_id: UUID,
    include_route_stops: bool = False,
    db: Session = Depends(get_db),
) -> schemas.ScenarioDetailResponse:
    """Return scenario detail."""

    scenario = ScenarioRepository(db).get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    if scenario.result is None and scenario.status == "processing":
        raise HTTPException(status_code=409, detail="Scenario is still processing.")
    return ResultService().build_detail_response(scenario, include_route_stops=include_route_stops)


@router.get("/{scenario_id}/routes", response_model=list[schemas.RouteDetailResponse])
def get_scenario_routes(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> list[schemas.RouteDetailResponse]:
    """Return route list for a scenario."""
    scenario = ScenarioRepository(db).get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    if scenario.result is None and scenario.status == "processing":
        raise HTTPException(status_code=409, detail="Scenario is still processing.")
    detail = ResultService().build_detail_response(scenario, include_route_stops=True)
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


@router.post(
    "/{scenario_id}/analysis",
    response_model=schemas.ScenarioAnalysisJobResponse,
    status_code=202,
)
def create_scenario_analysis(
    scenario_id: UUID,
    payload: schemas.ScenarioAnalysisCreateRequest,
    db: Session = Depends(get_db),
) -> schemas.ScenarioAnalysisJobResponse:
    """Create and queue a scenario analysis job."""

    job = ScenarioAnalysisService(db).create_job(scenario_id, payload)
    scenario_analysis_worker.submit(job.analysis_id)
    return job


@router.get("/{scenario_id}/analysis", response_model=schemas.ScenarioAnalysisQueryResponse)
def list_scenario_analysis_jobs(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> schemas.ScenarioAnalysisQueryResponse:
    """List scenario analysis jobs for a scenario."""

    return ScenarioAnalysisService(db).list_analysis_jobs(scenario_id)


@router.get(
    "/{scenario_id}/analysis/{analysis_id}",
    response_model=schemas.ScenarioAnalysisDetailResponse,
)
def get_scenario_analysis_detail(
    scenario_id: UUID,
    analysis_id: UUID,
    db: Session = Depends(get_db),
) -> schemas.ScenarioAnalysisDetailResponse:
    """Return a scenario analysis job detail."""

    return ScenarioAnalysisService(db).get_analysis_detail(scenario_id, analysis_id)


@router.delete("", response_model=schemas.DeleteScenariosResponse)
def delete_scenarios(
    payload: schemas.DeleteScenariosRequest,
    db: Session = Depends(get_db),
) -> schemas.DeleteScenariosResponse:
    """Delete selected scenarios and their dependent records."""

    deleted_count = ScenarioRepository(db).delete_scenarios(payload.scenario_ids)
    return schemas.DeleteScenariosResponse(deleted_count=deleted_count)
