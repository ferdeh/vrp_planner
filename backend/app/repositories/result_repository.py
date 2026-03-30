"""Result repository for optimization outputs."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import db_models, schemas


class ResultRepository:
    """Persistence operations for optimization results."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def save_result(
        self,
        scenario: db_models.Scenario,
        result: schemas.OptimizationResultResponse,
    ) -> db_models.OptimizationResult:
        scenario.status = result.status
        scenario.message = result.message
        if scenario.optimization_config:
            scenario.optimization_config.config_snapshot = result.objective_config.model_dump()

        db_result = db_models.OptimizationResult(
            scenario_id=scenario.id,
            status=result.status,
            message=result.message,
            total_orders=result.total_orders,
            total_demand=result.total_demand,
            total_delivered_demand=result.total_delivered_demand,
            total_unserved_orders=result.total_unserved_orders,
            active_truck_count=result.active_truck_count,
            total_distance=result.total_distance,
            total_time=result.total_time,
            total_cost=result.total_cost,
            solver_runtime_seconds=result.solver_runtime_seconds,
            preprocessing_notes=[note.model_dump() for note in result.preprocessing_notes],
            active_truck_type_summary=[item.model_dump() for item in result.active_truck_type_summary],
            routes=[
                db_models.OptimizationRoute(
                    truck_id=route.truck_id,
                    origin_name=route.origin_name,
                    origin_etd=route.origin_etd,
                    truck_type=route.truck_type,
                    capacity_kl=route.capacity_kl,
                    total_load=route.total_load,
                    utilization_percent=route.utilization_percent,
                    route_distance=route.route_distance,
                    route_time=route.route_time,
                    stop_count=route.stop_count,
                    stops=[
                        db_models.OptimizationRouteStop(
                            sequence=stop.sequence,
                            order_id=stop.order_id,
                            parent_order_id=stop.parent_order_id,
                            spbu_id=stop.spbu_id,
                            eta=stop.eta,
                            etd=stop.etd,
                            delivered_volume=stop.delivered_volume,
                            arrival_status=stop.arrival_status,
                        )
                        for stop in route.stops
                    ],
                )
                for route in result.route_details
            ],
            unserved_orders=[
                db_models.UnservedOrder(**item.model_dump(exclude={"constraint_details"}))
                for item in result.unserved_orders
            ],
        )
        scenario.result = db_result
        self.db.add(scenario)
        self.db.commit()
        self.db.refresh(db_result)
        return db_result
