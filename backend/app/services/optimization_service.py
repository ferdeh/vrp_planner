"""Scenario optimization orchestration."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import schemas
from app.repositories.result_repository import ResultRepository
from app.repositories.scenario_repository import ScenarioRepository
from app.repositories.settings_repository import SettingsRepository
from app.schemas.solver_setting_schema import SolverSettings
from app.services.constraint_service import ConstraintService
from app.services.solver_orchestrator import SolverOrchestrator

logger = logging.getLogger(__name__)


class OptimizationService:
    """Coordinate request validation, solving, and persistence."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings_repository = SettingsRepository(db)
        self.scenario_repository = ScenarioRepository(db)
        self.result_repository = ResultRepository(db)
        self.constraint_service = ConstraintService()
        self.solver_orchestrator = SolverOrchestrator(db)

    def _merge_config(self, payload: schemas.OptimizationRequest) -> schemas.OptimizationConfig:
        settings_row = self.settings_repository.get_active()
        settings_payload = schemas.SystemSettingsPayload(
            default_optimization_config=schemas.OptimizationConfig.model_validate(
                settings_row.default_optimization_config
            ),
            ui_preferences=settings_row.ui_preferences,
        )
        return self.constraint_service.merge_config(settings_payload, payload.optimization_config)

    def resolve_solver_settings(self, request_settings: SolverSettings | None) -> SolverSettings:
        return self.solver_orchestrator.resolve_solver_settings(request_settings)

    def create_job(
        self,
        payload: schemas.OptimizationRequest,
    ) -> tuple[schemas.OptimizationJobResponse, schemas.OptimizationRequest]:
        merged_config = self._merge_config(payload)
        prepared_payload = payload.model_copy(update={"optimization_config": merged_config})
        scenario = self.scenario_repository.create_scenario_snapshot(prepared_payload)
        return (
            schemas.OptimizationJobResponse(
                scenario_id=UUID(scenario.id),
                status="processing",
                message="Waiting for solver worker.",
                created_at=scenario.created_at,
            ),
            prepared_payload,
        )

    def process_job(
        self,
        scenario_id: UUID | str,
        payload: schemas.OptimizationRequest,
    ) -> None:
        scenario = self.scenario_repository.get_scenario(scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario {scenario_id} not found.")
        merged_config = payload.optimization_config or self._merge_config(payload)

        try:
            result = self.solver_orchestrator.solve(
                scenario=scenario,
                payload=payload,
                merged_config=merged_config,
            )
            self.result_repository.save_result(scenario, result)
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
