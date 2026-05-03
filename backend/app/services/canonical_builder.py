"""Build canonical VRP payloads for RouteFinder."""

from __future__ import annotations

from collections import defaultdict

from app.models import schemas as legacy_schemas
from app.schemas.canonical_vrp_schema import (
    CanonicalConstraints,
    CanonicalMatrices,
    CanonicalNode,
    CanonicalOrder,
    CanonicalScenario,
    CanonicalSettings,
    CanonicalVehicle,
    CanonicalVRPModel,
)
from app.schemas.solver_setting_schema import SolverSettings
from app.services.preprocessing_service import PreprocessedProblem
from app.utils.time_utils import hhmm_to_minutes, minutes_to_hhmm


class CanonicalBuilder:
    """Translate the existing optimization payload into the RouteFinder contract."""

    def build(
        self,
        *,
        scenario_id: str,
        payload: legacy_schemas.OptimizationRequest,
        problem: PreprocessedProblem,
        solver_settings: SolverSettings,
        solver_backbone: str,
    ) -> CanonicalVRPModel:
        node_counts: dict[str, int] = defaultdict(int)
        nodes: list[CanonicalNode] = [
            CanonicalNode(
                node_id=payload.depot_id,
                node_code=payload.depot_id,
                node_name=problem.depot_name,
                node_type="depot",
                time_window_start="00:00",
                time_window_end="23:59",
                supply_depot_ids=[payload.depot_id],
            )
        ]
        for order in payload.orders:
            if node_counts[order.spbu_id] > 0:
                continue
            node_counts[order.spbu_id] += 1
            spbu = problem.spbu_map[order.spbu_id]
            nodes.append(
                CanonicalNode(
                    node_id=order.spbu_id,
                    node_code=order.spbu_id,
                    node_name=spbu.name,
                    node_type="spbu",
                    lat=spbu.lat,
                    lng=spbu.lng,
                    truck_category=spbu.truck_category,
                    time_window_start=spbu.time_window_start,
                    time_window_end=spbu.time_window_end,
                    supply_depot_ids=spbu.supply_depot_ids,
                )
            )

        vehicles = []
        for truck in payload.available_trucks:
            shift_start = hhmm_to_minutes(truck.shift_start) or 0
            shift_end = hhmm_to_minutes(truck.shift_end) or shift_start
            max_working_minutes = max(0, shift_end - shift_start)
            if problem.config.max_vehicle_working_time_minutes is not None:
                max_working_minutes = min(max_working_minutes, problem.config.max_vehicle_working_time_minutes)
            vehicles.append(
                CanonicalVehicle(
                    vehicle_id=truck.truck_id,
                    depot_id=truck.start_depot_id,
                    end_depot_id=truck.end_depot_id,
                    truck_category=truck.truck_category,
                    truck_type=truck.truck_type,
                    capacity_kl=truck.capacity_kl,
                    compartments=[item.model_dump() for item in truck.compartments],
                    compatible_product_codes=truck.compatible_product_types,
                    max_working_minutes=max_working_minutes,
                    max_trips=max(1, len(problem.reload_nodes) + 1),
                    shift_start=truck.shift_start,
                    shift_end=truck.shift_end,
                    is_available=(truck.status or "").lower() not in {"inactive", "unavailable"},
                )
            )

        orders = []
        for shipment in problem.shipments:
            allowed_categories = sorted(
                {
                    truck.truck_category
                    for vehicle_index, truck in enumerate(payload.available_trucks)
                    if vehicle_index in shipment.allowed_vehicle_indices and truck.truck_category is not None
                }
            )
            spbu = problem.spbu_map.get(shipment.spbu_id)
            orders.append(
                CanonicalOrder(
                    order_id=shipment.order_id,
                    parent_order_id=shipment.parent_order_id,
                    node_id=shipment.spbu_id,
                    product_code=shipment.product_type,
                    quantity_kl=shipment.demand_kl,
                    service_time_minutes=shipment.service_time_minutes,
                    time_window_start=minutes_to_hhmm(shipment.time_window_start),
                    time_window_end=minutes_to_hhmm(shipment.time_window_end),
                    priority=shipment.priority,
                    eta=None if shipment.priority_eta_minutes is None else f"{shipment.priority_eta_minutes // 60:02d}:{shipment.priority_eta_minutes % 60:02d}",
                    allowed_truck_categories=allowed_categories,
                    supply_depot_compatibility=spbu.supply_depot_ids if spbu else [],
                )
            )

        return CanonicalVRPModel(
            scenario=CanonicalScenario(
                scenario_id=scenario_id,
                planning_date=str(payload.dispatch_date),
                depot_codes=[payload.depot_id],
            ),
            nodes=nodes,
            vehicles=vehicles,
            orders=orders,
            matrices=CanonicalMatrices(
                distance_matrix=problem.distance_matrix,
                duration_matrix=problem.time_matrix,
                node_ids=list(problem.matrix_positions.keys()),
            ),
            constraints=CanonicalConstraints(
                config=problem.config.model_dump(mode="json"),
                max_working_minutes=problem.config.max_vehicle_working_time_minutes,
                max_trips=max(1, len(problem.reload_nodes) + 1),
                allow_split_delivery=not problem.config.hard_constraints.no_split_order,
            ),
            settings=CanonicalSettings(
                solver_backbone=solver_backbone,
                use_routefinder=solver_settings.use_routefinder,
                cluster_mode=solver_settings.cluster_mode.value,
                max_cluster_size=solver_settings.max_cluster_size,
            ),
        )
