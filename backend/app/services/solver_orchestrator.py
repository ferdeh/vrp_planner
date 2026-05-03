"""Hybrid solver orchestration for RouteFinder + OR-Tools."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import db_models, schemas as legacy_schemas
from app.repositories.routefinder_clusters_repository import RouteFinderClustersRepository
from app.repositories.scenario_repository import ScenarioRepository
from app.repositories.solver_settings_repository import SolverSettingsRepository
from app.schemas.routefinder_cluster_schema import ClusterResult
from app.schemas.solver_setting_schema import SolverSettings
from app.services.canonical_builder import CanonicalBuilder
from app.services.preprocessing_service import PreprocessedProblem, PreprocessingService
from app.services.result_service import ResultService
from app.services.routefinder_client import RouteFinderClient
from app.services.routefinder_cluster_service import RouteFinderClusterService
from app.services.solution_validator import SolutionValidator
from app.services.solver_metrics_service import SolverMetricsService
from app.solver.ortools_solver import OrToolsSolver, SolverOutput

logger = logging.getLogger(__name__)


class SolverOrchestrator:
    """Coordinate preprocessing, RouteFinder warm start, OR-Tools, and validation."""

    def __init__(
        self,
        db: Session,
        *,
        preprocessing_service: PreprocessingService | None = None,
        routefinder_client: RouteFinderClient | None = None,
        routefinder_cluster_service: RouteFinderClusterService | None = None,
        solution_validator: SolutionValidator | None = None,
        solver: OrToolsSolver | None = None,
        result_service: ResultService | None = None,
        canonical_builder: CanonicalBuilder | None = None,
        metrics_service: SolverMetricsService | None = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        self.preprocessing_service = preprocessing_service or PreprocessingService()
        self.routefinder_client = routefinder_client or RouteFinderClient()
        self.routefinder_cluster_service = routefinder_cluster_service or RouteFinderClusterService()
        self.solution_validator = solution_validator or SolutionValidator()
        self.solver = solver or OrToolsSolver()
        self.result_service = result_service or ResultService()
        self.canonical_builder = canonical_builder or CanonicalBuilder()
        self.metrics_service = metrics_service or SolverMetricsService(db)
        self.solver_settings_repository = SolverSettingsRepository(db)
        self.scenario_repository = ScenarioRepository(db)
        self.routefinder_clusters_repository = RouteFinderClustersRepository(db)

    def resolve_solver_settings(self, request_settings: SolverSettings | None) -> SolverSettings:
        stored = self.solver_settings_repository.get_active()
        resolved = SolverSettings(
            use_routefinder=stored.use_routefinder,
            cluster_mode=stored.cluster_mode,
            max_cluster_size=stored.max_cluster_size,
        )
        if request_settings is None:
            return resolved
        return resolved.model_copy(update=request_settings.model_dump())

    def _build_preprocessing_only_result(
        self,
        *,
        scenario_id: str,
        payload: legacy_schemas.OptimizationRequest,
        problem: PreprocessedProblem,
    ) -> legacy_schemas.OptimizationResultResponse:
        return legacy_schemas.OptimizationResultResponse(
            scenario_id=scenario_id,
            status="infeasible"
            if not problem.config.soft_constraints.allow_unserved_orders
            else "preprocessing_failed",
            message="No feasible shipments remained after preprocessing.",
            total_orders=len(payload.orders),
            total_demand=problem.total_demand,
            total_delivered_demand=0,
            total_unserved_orders=len({item.parent_order_id for item in problem.preassigned_unserved}),
            active_truck_count=0,
            active_truck_type_summary=[],
            total_distance=0,
            total_time=0,
            total_cost=(
                len(problem.preassigned_unserved) * problem.config.penalties.unserved_order_penalty
                if problem.config.soft_constraints.allow_unserved_orders
                else 0
            ),
            total_penalty=(
                len(problem.preassigned_unserved) * problem.config.penalties.unserved_order_penalty
                if problem.config.soft_constraints.allow_unserved_orders
                else 0
            ),
            solver_runtime_seconds=0,
            objective_config=problem.config,
            route_details=[],
            unserved_orders=problem.preassigned_unserved,
            preprocessing_notes=problem.notes,
        )

    def solve(
        self,
        *,
        scenario: db_models.Scenario,
        payload: legacy_schemas.OptimizationRequest,
        merged_config: legacy_schemas.OptimizationConfig,
    ) -> legacy_schemas.OptimizationResultResponse:
        solver_settings = self.resolve_solver_settings(payload.solver_settings)
        solver_run = self.metrics_service.create_solver_run(
            scenario_id=scenario.id,
            settings=solver_settings,
        )
        routefinder_run = None
        routefinder_response: ClusterResult | None = None
        solver_output: SolverOutput | None = None

        try:
            self.scenario_repository.update_progress(scenario, "Building VRP model.")
            payload = payload.model_copy(update={"optimization_config": merged_config})
            problem = self.preprocessing_service.preprocess(payload, merged_config)

            if not problem.shipments and problem.preassigned_unserved:
                result = self._build_preprocessing_only_result(
                    scenario_id=scenario.id,
                    payload=payload,
                    problem=problem,
                )
            else:
                if solver_settings.use_routefinder:
                    self.scenario_repository.update_progress(scenario, "Generating RouteFinder SPBU clusters.")
                    routefinder_run = self.metrics_service.create_routefinder_run(
                        solver_run_id=solver_run.id,
                        settings=solver_settings,
                    )
                    canonical_model = self.canonical_builder.build(
                        scenario_id=scenario.id,
                        payload=payload,
                        problem=problem,
                        solver_settings=solver_settings,
                        solver_backbone=self.settings.solver_backbone,
                    )
                    try:
                        routefinder_response, routefinder_runtime = self.routefinder_client.generate_clusters(
                            canonical_model,
                            prefer_stub=self.settings.app_env.lower() == "test",
                        )
                        canonical_model = self.routefinder_cluster_service.inject_cluster_metadata(
                            canonical_model,
                            routefinder_response,
                        )
                        problem = self.routefinder_cluster_service.apply_clusters_to_problem(
                            problem,
                            routefinder_response,
                            cluster_mode=solver_settings.cluster_mode.value,
                        )
                        self.routefinder_clusters_repository.replace_for_scenario(
                            scenario.id,
                            routefinder_response.clusters,
                        )
                        self.metrics_service.update_routefinder_run(
                            routefinder_run,
                            runtime_seconds=routefinder_runtime,
                            status="SUCCESS",
                            response=routefinder_response,
                        )
                    except Exception as exc:
                        if routefinder_run is not None:
                            self.metrics_service.update_routefinder_run(
                                routefinder_run,
                                runtime_seconds=0,
                                status="FAILED",
                                response=routefinder_response,
                                error_message=str(exc),
                            )
                        logger.warning("RouteFinder failed for scenario %s, falling back to OR-Tools only: %s", scenario.id, exc)

                self.scenario_repository.update_progress(scenario, "Refining solution with OR-Tools.")
                solver_output = self.solver.solve(problem)
                result = self.result_service.build_response(scenario.id, problem, solver_output)
                self.scenario_repository.update_progress(scenario, "Running final validation.")
                final_validation = self.solution_validator.validate(
                    payload=payload,
                    problem=problem,
                    result=result,
                )
                self.metrics_service.save_validation(
                    solver_run_id=solver_run.id,
                        validation_type="final_solution",
                        validation=final_validation,
                )
                if not final_validation.is_valid:
                    raise ValueError("Final solution validation failed.")

            self.metrics_service.update_solver_run(
                solver_run,
                result=result,
                routefinder_response=routefinder_response,
                runtime_seconds=0 if solver_output is None else solver_output.runtime_seconds,
                status=result.status,
            )
            return result
        except Exception as exc:
            self.metrics_service.update_solver_run(
                solver_run,
                result=None,
                routefinder_response=routefinder_response,
                runtime_seconds=0 if solver_output is None else solver_output.runtime_seconds,
                status="error",
                error_message=str(exc),
            )
            raise
