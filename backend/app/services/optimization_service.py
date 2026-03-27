"""Scenario optimization orchestration."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import schemas
from app.repositories.result_repository import ResultRepository
from app.repositories.scenario_repository import ScenarioRepository
from app.repositories.settings_repository import SettingsRepository
from app.services.constraint_service import ConstraintService
from app.services.preprocessing_service import PreprocessingService
from app.services.result_service import ResultService
from app.solver.ortools_solver import OrToolsSolver, SolverOutput

logger = logging.getLogger(__name__)


class OptimizationService:
    """Coordinate request validation, solving, and persistence."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings_repository = SettingsRepository(db)
        self.scenario_repository = ScenarioRepository(db)
        self.result_repository = ResultRepository(db)
        self.constraint_service = ConstraintService()
        self.preprocessing_service = PreprocessingService()
        self.solver = OrToolsSolver()
        self.result_service = ResultService()

    def optimize(self, payload: schemas.OptimizationRequest) -> schemas.OptimizationResultResponse:
        settings_row = self.settings_repository.get_active()
        settings_payload = schemas.SystemSettingsPayload(
            default_optimization_config=schemas.OptimizationConfig.model_validate(
                settings_row.default_optimization_config
            ),
            ui_preferences=settings_row.ui_preferences,
        )
        merged_config = self.constraint_service.merge_config(settings_payload, payload.optimization_config)
        scenario_snapshot = payload.model_copy(update={"optimization_config": merged_config})
        scenario = self.scenario_repository.create_scenario_snapshot(scenario_snapshot)

        try:
            problem = self.preprocessing_service.preprocess(payload, merged_config)
            if not problem.shipments and problem.preassigned_unserved:
                solver_output = SolverOutput(
                    built_model=None,  # type: ignore[arg-type]
                    assignment=None,
                    runtime_seconds=0.0,
                    message="No feasible shipments remained after preprocessing.",
                )
                result = schemas.OptimizationResultResponse(
                    scenario_id=scenario.id,
                    status="infeasible" if not merged_config.soft_constraints.allow_unserved_orders else "partial",
                    message=solver_output.message,
                    total_orders=len(payload.orders),
                    total_demand=problem.total_demand,
                    total_delivered_demand=0,
                    total_unserved_orders=len({item.parent_order_id for item in problem.preassigned_unserved}),
                    active_truck_count=0,
                    active_truck_type_summary=[],
                    total_distance=0,
                    total_time=0,
                    total_cost=(
                        len(problem.preassigned_unserved) * merged_config.penalties.unserved_order_penalty
                        if merged_config.soft_constraints.allow_unserved_orders
                        else 0
                    ),
                    total_penalty=(
                        len(problem.preassigned_unserved) * merged_config.penalties.unserved_order_penalty
                        if merged_config.soft_constraints.allow_unserved_orders
                        else 0
                    ),
                    solver_runtime_seconds=0,
                    objective_config=merged_config,
                    route_details=[],
                    unserved_orders=problem.preassigned_unserved,
                    preprocessing_notes=problem.notes,
                )
            else:
                solver_output = self.solver.solve(problem)
                result = self.result_service.build_response(scenario.id, problem, solver_output)
            self.result_repository.save_result(scenario, result)
            return result
        except Exception as exc:
            logger.exception("Optimization failed for scenario %s", scenario.id)
            error_result = schemas.OptimizationResultResponse(
                scenario_id=scenario.id,
                status="error",
                message=str(exc),
                total_orders=len(payload.orders),
                total_demand=round(sum(order.demand_kl for order in payload.orders), 2),
                total_delivered_demand=0,
                total_unserved_orders=len(payload.orders),
                active_truck_count=0,
                active_truck_type_summary=[],
                total_distance=0,
                total_time=0,
                total_cost=0,
                total_penalty=0,
                solver_runtime_seconds=0,
                objective_config=merged_config,
                route_details=[],
                unserved_orders=[
                    schemas.UnservedOrderDetail(
                        order_id=order.order_id,
                        parent_order_id=order.order_id,
                        spbu_id=order.spbu_id,
                        demand_kl=order.demand_kl,
                        reason=str(exc),
                    )
                    for order in payload.orders
                ],
                preprocessing_notes=[],
            )
            self.result_repository.save_result(scenario, error_result)
            return error_result
