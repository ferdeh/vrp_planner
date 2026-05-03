"""Hybrid VRP solver routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import schemas as legacy_schemas
from app.repositories.scenario_repository import ScenarioRepository
from app.schemas.cluster_metric_schema import ClusterMetricsResponse
from app.repositories.solver_settings_repository import SolverSettingsRepository
from app.schemas.solution_schema import SolverJobResponse
from app.schemas.solver_setting_schema import SolverSettings, SolverSettingsResponse
from app.services.cluster_metrics_service import ClusterMetricsService
from app.services.optimization_service import OptimizationService
from app.services.optimization_worker import optimization_worker

router = APIRouter(prefix="/api/vrp", tags=["vrp"])


@router.get("/solver-settings", response_model=SolverSettingsResponse)
def get_solver_settings(db: Session = Depends(get_db)) -> SolverSettingsResponse:
    instance = SolverSettingsRepository(db).get_active()
    return SolverSettingsResponse(
        id=UUID(instance.id),
        tenant_id=None if instance.tenant_id is None else UUID(instance.tenant_id),
        use_routefinder=instance.use_routefinder,
        cluster_mode=instance.cluster_mode,
        max_cluster_size=instance.max_cluster_size,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


@router.put("/solver-settings", response_model=SolverSettingsResponse)
def update_solver_settings(
    payload: SolverSettings,
    db: Session = Depends(get_db),
) -> SolverSettingsResponse:
    instance = SolverSettingsRepository(db).update(payload)
    return SolverSettingsResponse(
        id=UUID(instance.id),
        tenant_id=None if instance.tenant_id is None else UUID(instance.tenant_id),
        use_routefinder=instance.use_routefinder,
        cluster_mode=instance.cluster_mode,
        max_cluster_size=instance.max_cluster_size,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


@router.post("/solve", response_model=SolverJobResponse, status_code=status.HTTP_202_ACCEPTED)
def solve_vrp(
    payload: legacy_schemas.OptimizationRequest,
    db: Session = Depends(get_db),
) -> SolverJobResponse:
    service = OptimizationService(db)
    job, prepared_payload = service.create_job(payload)
    optimization_worker.submit(job.scenario_id, prepared_payload)
    resolved_settings = service.resolve_solver_settings(prepared_payload.solver_settings)
    return SolverJobResponse(
        scenario_id=job.scenario_id,
        status=job.status,
        message=job.message,
        created_at=job.created_at,
        solver_mode="Hybrid: RouteFinder Clustering + OR-Tools" if resolved_settings.use_routefinder else "OR-Tools Only",
        solver_settings=resolved_settings,
    )


@router.get("/cluster-metrics", response_model=ClusterMetricsResponse)
def get_cluster_metrics(
    scenario_id: UUID = Query(...),
    db: Session = Depends(get_db),
) -> ClusterMetricsResponse:
    scenario = ScenarioRepository(db).get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    if scenario.result is None and scenario.status == "processing":
        raise HTTPException(status_code=409, detail="Scenario is still processing.")
    return ClusterMetricsService(db).get_cluster_metrics(scenario_id)
