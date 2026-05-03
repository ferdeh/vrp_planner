"""Persistence helpers for hybrid solver metrics."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import db_models, schemas as legacy_schemas
from app.repositories.routefinder_runs_repository import RouteFinderRunsRepository
from app.repositories.solver_runs_repository import SolverRunsRepository
from app.schemas.routefinder_cluster_schema import ClusterResult
from app.schemas.solution_schema import FinalSolutionValidationResult
from app.schemas.solver_setting_schema import SolverSettings


class SolverMetricsService:
    """Record solver, RouteFinder, and validation metrics."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.solver_runs_repository = SolverRunsRepository(db)
        self.routefinder_runs_repository = RouteFinderRunsRepository(db)

    @staticmethod
    def solver_mode(settings: SolverSettings) -> str:
        return "hybrid_routefinder_cluster_ortools" if settings.use_routefinder else "ortools_only"

    @staticmethod
    def _initial_score(_response: ClusterResult | None) -> float | None:
        return None

    @staticmethod
    def _improvement_percent(initial_score: float | None, final_score: float | None) -> float | None:
        if initial_score in (None, 0) or final_score is None:
            return None
        return round(((initial_score - final_score) / initial_score) * 100, 4)

    def create_solver_run(
        self,
        *,
        scenario_id: str,
        settings: SolverSettings,
    ) -> db_models.VRPSolverRun:
        return self.solver_runs_repository.create_run(
            scenario_id=scenario_id,
            solver_mode=self.solver_mode(settings),
            routefinder_enabled=settings.use_routefinder,
            status="processing",
        )

    def update_solver_run(
        self,
        solver_run: db_models.VRPSolverRun,
        *,
        result: legacy_schemas.OptimizationResultResponse | None = None,
        routefinder_response: ClusterResult | None = None,
        runtime_seconds: float | None = None,
        status: str,
        error_message: str | None = None,
    ) -> db_models.VRPSolverRun:
        initial_score = self._initial_score(routefinder_response)
        final_score = None if result is None else float(result.total_cost)
        return self.solver_runs_repository.update_run(
            solver_run,
            initial_solution_score=initial_score,
            final_solution_score=final_score,
            improvement_percent=self._improvement_percent(initial_score, final_score),
            runtime_seconds=runtime_seconds,
            status=status,
            error_message=error_message,
        )

    def create_routefinder_run(
        self,
        *,
        solver_run_id: str | None,
        settings: SolverSettings,
    ) -> db_models.VRPRouteFinderRun:
        return self.routefinder_runs_repository.create_run(
            solver_run_id=solver_run_id,
            enabled=settings.use_routefinder,
            status="processing",
            cluster_mode=settings.cluster_mode.value,
            runtime_seconds=0,
            max_cluster_size=settings.max_cluster_size,
        )

    def update_routefinder_run(
        self,
        routefinder_run: db_models.VRPRouteFinderRun,
        *,
        runtime_seconds: float,
        status: str,
        response: ClusterResult | None = None,
        error_message: str | None = None,
    ) -> db_models.VRPRouteFinderRun:
        return self.routefinder_runs_repository.update_run(
            routefinder_run,
            runtime_seconds=runtime_seconds,
            status=status,
            cluster_count=0 if response is None else len(response.clusters),
            total_clustered_demand_kl=0
            if response is None
            else round(sum(cluster.total_demand_kl for cluster in response.clusters), 2),
            error_message=error_message,
        )

    def save_validation(
        self,
        *,
        solver_run_id: str,
        validation_type: str,
        validation: FinalSolutionValidationResult,
    ) -> db_models.VRPSolutionValidation:
        instance = db_models.VRPSolutionValidation(
            solver_run_id=solver_run_id,
            validation_type=validation_type,
            status=validation.status,
            hard_constraint_violations=validation.hard_constraint_violations,
            soft_constraint_penalties=validation.soft_constraint_penalties,
        )
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance
