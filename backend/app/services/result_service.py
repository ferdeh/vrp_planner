"""Map solver outputs into API responses."""

from __future__ import annotations

from collections import Counter, defaultdict
from uuid import UUID

from app.models import schemas
from app.services.master_data_client import MasterDataClient
from app.services.network_client import NetworkClient
from app.services.preprocessing_service import PreprocessedProblem
from app.solver.ortools_solver import SolverOutput
from app.utils.time_utils import hhmm_to_minutes, minutes_to_hhmm


class ResultService:
    """Build external response and persistence DTOs from solver results."""

    def __init__(
        self,
        master_data_client: MasterDataClient | None = None,
        network_client: NetworkClient | None = None,
    ) -> None:
        self.master_data_client = master_data_client or MasterDataClient()
        self.network_client = network_client or NetworkClient(self.master_data_client)

    def _get_leg_audit_safe(self, origin_id: str, destination_id: str) -> dict[str, str | float | None]:
        try:
            return self.network_client.get_leg_audit(origin_id, destination_id)
        except Exception:
            return {
                "travel_path": f"{origin_id} -> {destination_id}",
                "segment_max_velocity_kmh": "-",
                "travel_distance_km": None,
                "travel_time_minutes": None,
            }

    def _calculate_detail_penalty(
        self,
        config: schemas.OptimizationConfig,
        routes: list[schemas.RouteDetailResponse],
        unserved_orders: list[schemas.UnservedOrderDetail],
        input_orders: list[schemas.OrderInput],
        input_trucks: list[schemas.TruckInput],
        depot_operation_window_start: str | None = None,
        depot_operation_window_end: str | None = None,
    ) -> float:
        order_by_id = {item.order_id: item for item in input_orders}
        truck_by_id = {item.truck_id: item for item in input_trucks}
        total_penalty = 0.0

        if config.soft_constraints.allow_unserved_orders:
            total_penalty += len(unserved_orders) * config.penalties.unserved_order_penalty

        if config.soft_constraints.time_window:
            for route in routes:
                for stop in route.stops:
                    if stop.stop_kind != "delivery":
                        continue
                    order = order_by_id.get(stop.parent_order_id) or order_by_id.get(stop.order_id)
                    if order is None:
                        continue
                    eta_minutes = hhmm_to_minutes(stop.eta)
                    window_end_minutes = hhmm_to_minutes(order.time_window_end)
                    if eta_minutes is None or window_end_minutes is None:
                        continue
                    total_penalty += max(0, eta_minutes - window_end_minutes) * config.penalties.late_arrival_penalty_per_minute

        if config.soft_constraints.priority_eta:
            for route in routes:
                for stop in route.stops:
                    if stop.stop_kind != "delivery":
                        continue
                    order = order_by_id.get(stop.parent_order_id) or order_by_id.get(stop.order_id)
                    if order is None or not order.priority or not order.eta:
                        continue
                    eta_minutes = hhmm_to_minutes(stop.eta)
                    priority_eta_minutes = hhmm_to_minutes(order.eta)
                    if eta_minutes is None or priority_eta_minutes is None:
                        continue
                    total_penalty += (
                        max(0, eta_minutes - priority_eta_minutes)
                        * config.penalties.priority_eta_penalty_per_minute
                    )

        for route in routes:
            truck = truck_by_id.get(route.truck_id)
            if truck is None or not truck.shift_end or not route.return_eta:
                continue
            return_minutes = hhmm_to_minutes(route.return_eta)
            shift_end_minutes = hhmm_to_minutes(truck.shift_end)
            if return_minutes is None or shift_end_minutes is None:
                continue
            total_penalty += max(0, return_minutes - shift_end_minutes) * config.penalties.overtime_penalty_per_minute

        if config.soft_constraints.depot_operation_window and depot_operation_window_start and depot_operation_window_end:
            _, operation_start, operation_end = self._calculate_depot_operation_window(routes)
            if operation_start and operation_end:
                total_penalty += self._calculate_depot_operation_window_penalty(
                    operation_start=operation_start,
                    operation_end=operation_end,
                    window_start=depot_operation_window_start,
                    window_end=depot_operation_window_end,
                    penalty_per_minute=config.penalties.depot_operation_window_penalty_per_minute,
                )

        return round(total_penalty, 2)

    def _derive_origin_service_start(
        self,
        origin_etd: str | None,
        depot_service_time_minutes: int,
    ) -> str | None:
        if not origin_etd:
            return None
        return minutes_to_hhmm(max(0, hhmm_to_minutes(origin_etd) - depot_service_time_minutes))

    def _derive_return_eta(
        self,
        origin_service_start: str | None,
        route_time: float,
    ) -> str | None:
        if not origin_service_start:
            return None
        return minutes_to_hhmm(hhmm_to_minutes(origin_service_start) + int(round(route_time)))

    def _calculate_depot_operation_window(
        self,
        routes: list[schemas.RouteDetailResponse],
    ) -> tuple[int, str | None, str | None]:
        service_windows: list[tuple[int, int]] = []

        for route in routes:
            if route.origin_service_start and route.origin_etd:
                service_windows.append(
                    (
                        hhmm_to_minutes(route.origin_service_start),
                        hhmm_to_minutes(route.origin_etd),
                    )
                )
            for stop in route.stops:
                if stop.stop_kind != "depot_reload":
                    continue
                service_windows.append((hhmm_to_minutes(stop.eta), hhmm_to_minutes(stop.etd)))

        if not service_windows:
            return 0, None, None

        start_minute = min(start for start, _ in service_windows)
        end_minute = max(end for _, end in service_windows)
        return end_minute - start_minute, minutes_to_hhmm(start_minute), minutes_to_hhmm(end_minute)

    def _calculate_depot_operation_window_penalty(
        self,
        operation_start: str,
        operation_end: str,
        window_start: str,
        window_end: str,
        penalty_per_minute: float,
    ) -> float:
        operation_start_minutes = hhmm_to_minutes(operation_start)
        operation_end_minutes = hhmm_to_minutes(operation_end)
        window_start_minutes = hhmm_to_minutes(window_start)
        window_end_minutes = hhmm_to_minutes(window_end)
        if None in {
            operation_start_minutes,
            operation_end_minutes,
            window_start_minutes,
            window_end_minutes,
        }:
            return 0.0
        early_violation = max(0, window_start_minutes - operation_start_minutes)
        late_violation = max(0, operation_end_minutes - window_end_minutes)
        return (early_violation + late_violation) * penalty_per_minute

    def build_response(
        self,
        scenario_id: str | UUID,
        problem: PreprocessedProblem,
        solver_output: SolverOutput,
    ) -> schemas.OptimizationResultResponse:
        assignment = solver_output.assignment
        routing = solver_output.built_model.routing
        manager = solver_output.built_model.manager
        time_dimension = solver_output.built_model.time_dimension
        distance_dimension = solver_output.built_model.distance_dimension

        visited_orders: set[str] = set()
        route_details: list[schemas.RouteDetailResponse] = []
        active_types: Counter[str] = Counter()
        active_capacity_by_type: dict[str, float] = defaultdict(float)
        total_distance = 0.0
        total_time = 0.0
        total_cost = 0.0
        total_penalty = 0.0
        delivered_demand = 0.0

        if assignment:
            for vehicle_id, truck in enumerate(problem.trucks):
                index = routing.Start(vehicle_id)
                stops: list[schemas.RouteStopResponse] = []
                route_load = 0.0
                route_late_penalty = 0.0
                sequence = 1
                trip_sequence = 1
                reload_sequence = 0
                while not routing.IsEnd(index):
                    node = manager.IndexToNode(index)
                    next_index = assignment.Value(routing.NextVar(index))
                    node_detail = problem.get_node(node)
                    if node_detail is not None:
                        eta = assignment.Value(time_dimension.CumulVar(index))
                        etd = eta + node_detail.service_time_minutes
                        previous_node_name = problem.depot_id if sequence == 1 else stops[-1].spbu_id
                        leg_audit = self._get_leg_audit_safe(previous_node_name, node_detail.spbu_id)
                        if node_detail.node_kind == "shipment":
                            visited_orders.add(node_detail.order_id)
                            route_load += node_detail.demand_kl
                            delivered_demand += node_detail.demand_kl
                            lateness = max(0, eta - node_detail.time_window_end)
                            route_late_penalty += (
                                lateness * problem.config.penalties.late_arrival_penalty_per_minute
                            )
                            stop_kind = "delivery"
                            arrival_status = "late" if lateness > 0 else "on_time"
                            delivered_volume = node_detail.demand_kl
                        else:
                            trip_sequence += 1
                            reload_sequence += 1
                            stop_kind = "depot_reload"
                            arrival_status = "reloaded_at_depot"
                            delivered_volume = 0.0
                        stops.append(
                            schemas.RouteStopResponse(
                                sequence=sequence,
                                order_id=(
                                    f"DEPOT_RELOAD#{reload_sequence}"
                                    if node_detail.node_kind == "reload"
                                    else node_detail.order_id
                                ),
                                parent_order_id=node_detail.parent_order_id,
                                spbu_id=node_detail.spbu_id,
                                stop_kind=stop_kind,
                                trip_sequence=trip_sequence,
                                spbu_name=problem.depot_name
                                if node_detail.node_kind == "reload"
                                else (
                                    problem.spbu_map.get(node_detail.spbu_id).name
                                    if problem.spbu_map.get(node_detail.spbu_id)
                                    else None
                                ),
                                travel_path=str(leg_audit.get("travel_path") or ""),
                                segment_max_velocity_kmh=str(leg_audit.get("segment_max_velocity_kmh") or "-"),
                                travel_distance_km=float(leg_audit["travel_distance_km"]) if leg_audit.get("travel_distance_km") is not None else None,
                                travel_time_minutes=float(leg_audit["travel_time_minutes"]) if leg_audit.get("travel_time_minutes") is not None else None,
                                eta=minutes_to_hhmm(int(eta)),
                                etd=minutes_to_hhmm(int(etd)),
                                delivered_volume=delivered_volume,
                                arrival_status=arrival_status,
                            )
                        )
                        sequence += 1
                    index = next_index

                if stops:
                    end_time = assignment.Value(time_dimension.CumulVar(routing.End(vehicle_id)))
                    start_time = assignment.Value(time_dimension.CumulVar(routing.Start(vehicle_id)))
                    route_time = max(0, end_time - start_time) + problem.depot_service_time_minutes
                    route_distance = assignment.Value(distance_dimension.CumulVar(routing.End(vehicle_id)))
                    overtime_limit = int(problem.trucks[vehicle_id].shift_end.split(":")[0]) * 60 + int(
                        problem.trucks[vehicle_id].shift_end.split(":")[1]
                    )
                    overtime_minutes = max(0, end_time - overtime_limit)
                    overtime_penalty = overtime_minutes * problem.config.penalties.overtime_penalty_per_minute
                    total_penalty += route_late_penalty + overtime_penalty
                    route_cost = (
                        problem.trucks[vehicle_id].fixed_cost
                        + route_distance * problem.trucks[vehicle_id].variable_cost_per_km
                        + route_time * problem.trucks[vehicle_id].variable_cost_per_minute
                        + route_late_penalty
                        + overtime_penalty
                    )
                    return_leg_audit = self._get_leg_audit_safe(stops[-1].spbu_id, problem.depot_id)
                    total_distance += route_distance
                    total_time += route_time
                    total_cost += route_cost
                    active_types[truck.truck_type] += 1
                    active_capacity_by_type[truck.truck_type] += truck.capacity_kl
                    route_details.append(
                        schemas.RouteDetailResponse(
                            truck_id=truck.truck_id,
                            no_polisi=truck.no_polisi,
                            origin_name=problem.depot_name,
                            origin_service_start=minutes_to_hhmm(
                                int(max(0, start_time - problem.depot_service_time_minutes))
                            ),
                            origin_etd=minutes_to_hhmm(int(start_time)),
                            depot_service_time_minutes=problem.depot_service_time_minutes,
                            depot_gate_limit=problem.depot_gate_limit,
                            return_eta=minutes_to_hhmm(int(end_time)),
                            return_path=str(return_leg_audit.get("travel_path") or ""),
                            return_segment_max_velocity_kmh=str(
                                return_leg_audit.get("segment_max_velocity_kmh") or "-"
                            ),
                            return_distance_km=float(return_leg_audit["travel_distance_km"])
                            if return_leg_audit.get("travel_distance_km") is not None
                            else None,
                            return_travel_time_minutes=float(return_leg_audit["travel_time_minutes"])
                            if return_leg_audit.get("travel_time_minutes") is not None
                            else None,
                            truck_type=truck.truck_type,
                            capacity_kl=truck.capacity_kl,
                            total_load=round(route_load, 2),
                            utilization_percent=round(
                                (
                                    min(
                                        truck.capacity_kl,
                                        max(
                                            (
                                                sum(
                                                    stop.delivered_volume
                                                    for stop in stops
                                                    if stop.trip_sequence == trip_number
                                                )
                                                for trip_number in range(1, trip_sequence + 1)
                                            ),
                                            default=0.0,
                                        ),
                                    )
                                    / truck.capacity_kl
                                )
                                * 100,
                                2,
                            ),
                            route_distance=round(route_distance, 2),
                            route_time=round(route_time, 2),
                            stop_count=len(stops),
                            trip_count=trip_sequence,
                            stops=stops,
                        )
                    )

        unserved = list(problem.preassigned_unserved)
        dropped_penalty = 0.0
        for shipment in problem.shipments:
            if shipment.order_id not in visited_orders:
                unserved.append(
                    schemas.UnservedOrderDetail(
                        order_id=shipment.order_id,
                        parent_order_id=shipment.parent_order_id,
                        spbu_id=shipment.spbu_id,
                        demand_kl=shipment.demand_kl,
                        reason="Dropped by solver with penalty." if assignment else solver_output.message,
                    )
                )
                if problem.config.soft_constraints.allow_unserved_orders:
                    dropped_penalty += problem.config.penalties.unserved_order_penalty

        total_cost += dropped_penalty
        total_penalty += dropped_penalty
        active_summary = [
            schemas.TruckTypeSummary(
                truck_type=truck_type,
                active_count=count,
                total_capacity_kl=round(active_capacity_by_type[truck_type], 2),
            )
            for truck_type, count in sorted(active_types.items())
        ]
        served_all = not unserved
        total_depot_operation_time_minutes, depot_operation_start, depot_operation_end = (
            self._calculate_depot_operation_window(route_details)
        )
        priority_eta_penalty = 0.0
        if problem.config.soft_constraints.priority_eta:
            order_by_id = {item.order_id: item for item in problem.orders}
            for route in route_details:
                for stop in route.stops:
                    if stop.stop_kind != "delivery":
                        continue
                    order = order_by_id.get(stop.parent_order_id) or order_by_id.get(stop.order_id)
                    if order is None or not order.priority or not order.eta:
                        continue
                    eta_minutes = hhmm_to_minutes(stop.eta)
                    priority_eta_minutes = hhmm_to_minutes(order.eta)
                    if eta_minutes is None or priority_eta_minutes is None:
                        continue
                    priority_eta_penalty += (
                        max(0, eta_minutes - priority_eta_minutes)
                        * problem.config.penalties.priority_eta_penalty_per_minute
                    )
        total_penalty += priority_eta_penalty
        total_cost += priority_eta_penalty
        depot_operation_window_penalty = 0.0
        if (
            problem.config.soft_constraints.depot_operation_window
            and depot_operation_start
            and depot_operation_end
        ):
            depot_operation_window_penalty = self._calculate_depot_operation_window_penalty(
                operation_start=depot_operation_start,
                operation_end=depot_operation_end,
                window_start=minutes_to_hhmm(problem.depot_operation_window_start),
                window_end=minutes_to_hhmm(problem.depot_operation_window_end),
                penalty_per_minute=problem.config.penalties.depot_operation_window_penalty_per_minute,
            )
            total_penalty += depot_operation_window_penalty
            total_cost += depot_operation_window_penalty
        if assignment is None:
            status: schemas.SolutionStatus = "infeasible"
        elif served_all:
            status = "feasible"
        else:
            status = "partial"
        if assignment is None and not problem.config.soft_constraints.allow_unserved_orders:
            status = "infeasible"

        return schemas.OptimizationResultResponse(
            scenario_id=UUID(str(scenario_id)),
            status=status,
            message=solver_output.message,
            total_orders=len(problem.orders),
            total_demand=problem.total_demand,
            total_delivered_demand=round(delivered_demand, 2),
            total_unserved_orders=len({item.parent_order_id for item in unserved}),
            active_truck_count=len(route_details),
            active_truck_type_summary=active_summary,
            total_distance=round(total_distance, 2),
            total_time=round(total_time, 2),
            total_cost=round(total_cost, 2),
            total_penalty=round(total_penalty, 2),
            total_depot_operation_time_minutes=total_depot_operation_time_minutes,
            depot_operation_start=depot_operation_start,
            depot_operation_end=depot_operation_end,
            solver_runtime_seconds=round(solver_output.runtime_seconds, 4),
            objective_config=problem.config,
            route_details=route_details,
            unserved_orders=unserved,
            preprocessing_notes=problem.notes,
        )

    def build_detail_response(
        self,
        scenario,
    ) -> schemas.ScenarioDetailResponse:
        """Map persisted scenario ORM object to response schema."""

        result = scenario.result
        if result is None or scenario.optimization_config is None:
            raise ValueError("Scenario result is not available.")
        truck_no_polisi_by_id = {item.truck_id: item.no_polisi for item in scenario.trucks}
        try:
            depot = self.master_data_client.get_depot(scenario.depot_id)
            depot_name = depot.name
            depot_gate_limit = depot.gate_limit
            depot_operation_window_start = depot.time_window_start
            depot_operation_window_end = depot.time_window_end
        except Exception:
            depot_name = scenario.depot_id
            depot_gate_limit = None
            depot_operation_window_start = "00:00"
            depot_operation_window_end = "23:59"
        route_stop_spbu_ids = {stop.spbu_id for route in result.routes for stop in route.stops}
        try:
            spbu_name_by_id = {
                spbu_id: item.name
                for spbu_id, item in self.master_data_client.get_spbu_many(
                    list(route_stop_spbu_ids),
                    depot_id=scenario.depot_id,
                ).items()
            }
        except Exception:
            spbu_name_by_id = {}
        objective_config = schemas.OptimizationConfig.model_validate(
            scenario.optimization_config.config_snapshot
        )
        depot_service_time_minutes = int(scenario.raw_request.get("depot_service_time_minutes") or 0)
        route_stops = []
        for route in result.routes:
            ordered_stops = sorted(route.stops, key=lambda item: item.sequence)
            enriched_stops: list[schemas.RouteStopResponse] = []
            previous_node_name = scenario.depot_id
            trip_sequence = 1
            reload_sequence = 0
            for stop in ordered_stops:
                leg_audit = self._get_leg_audit_safe(previous_node_name, stop.spbu_id)
                stop_kind = "depot_reload" if stop.order_id.startswith("DEPOT_RELOAD#") else "delivery"
                if stop_kind == "depot_reload":
                    trip_sequence += 1
                    reload_sequence += 1
                enriched_stops.append(
                    schemas.RouteStopResponse(
                        sequence=stop.sequence,
                        order_id=f"DEPOT_RELOAD#{reload_sequence}" if stop_kind == "depot_reload" else stop.order_id,
                        parent_order_id=stop.parent_order_id,
                        spbu_id=stop.spbu_id,
                        stop_kind=stop_kind,
                        trip_sequence=trip_sequence,
                        spbu_name=depot_name if stop_kind == "depot_reload" else spbu_name_by_id.get(stop.spbu_id),
                        travel_path=str(leg_audit.get("travel_path") or ""),
                        segment_max_velocity_kmh=str(leg_audit.get("segment_max_velocity_kmh") or "-"),
                        travel_distance_km=float(leg_audit["travel_distance_km"]) if leg_audit.get("travel_distance_km") is not None else None,
                        travel_time_minutes=float(leg_audit["travel_time_minutes"]) if leg_audit.get("travel_time_minutes") is not None else None,
                        eta=stop.eta,
                        etd=stop.etd,
                        delivered_volume=stop.delivered_volume,
                        arrival_status=stop.arrival_status,
                    )
                )
                previous_node_name = stop.spbu_id
            return_leg_audit = (
                self._get_leg_audit_safe(ordered_stops[-1].spbu_id, scenario.depot_id)
                if ordered_stops
                else {
                    "travel_path": "",
                    "segment_max_velocity_kmh": "-",
                    "travel_distance_km": None,
                    "travel_time_minutes": None,
                }
            )
            route_stops.append((route, enriched_stops, return_leg_audit))
        route_details = [
            schemas.RouteDetailResponse(
                truck_id=route.truck_id,
                no_polisi=truck_no_polisi_by_id.get(route.truck_id),
                origin_name=route.origin_name or depot_name,
                origin_service_start=self._derive_origin_service_start(
                    route.origin_etd,
                    depot_service_time_minutes,
                ),
                origin_etd=route.origin_etd,
                depot_service_time_minutes=depot_service_time_minutes,
                depot_gate_limit=depot_gate_limit,
                return_eta=self._derive_return_eta(
                    self._derive_origin_service_start(route.origin_etd, depot_service_time_minutes),
                    route.route_time,
                ),
                return_path=str(return_leg_audit.get("travel_path") or ""),
                return_segment_max_velocity_kmh=str(
                    return_leg_audit.get("segment_max_velocity_kmh") or "-"
                ),
                return_distance_km=float(return_leg_audit["travel_distance_km"])
                if return_leg_audit.get("travel_distance_km") is not None
                else None,
                return_travel_time_minutes=float(return_leg_audit["travel_time_minutes"])
                if return_leg_audit.get("travel_time_minutes") is not None
                else None,
                truck_type=route.truck_type,
                capacity_kl=route.capacity_kl,
                total_load=route.total_load,
                utilization_percent=route.utilization_percent,
                route_distance=route.route_distance,
                route_time=route.route_time,
                stop_count=route.stop_count,
                trip_count=max((stop.trip_sequence for stop in stops), default=1),
                stops=stops,
            )
            for route, stops, return_leg_audit in route_stops
        ]
        unserved_orders = [
            schemas.UnservedOrderDetail(
                order_id=item.order_id,
                parent_order_id=item.parent_order_id,
                spbu_id=item.spbu_id,
                demand_kl=item.demand_kl,
                reason=item.reason,
            )
            for item in result.unserved_orders
        ]
        input_orders = [
            schemas.OrderInput(
                order_id=item.order_id,
                spbu_id=item.spbu_id,
                product_type=item.product_type,
                demand_kl=item.demand_kl,
                priority=item.priority,
                eta=item.eta,
                service_time_minutes=item.service_time_minutes,
                time_window_start=item.time_window_start,
                time_window_end=item.time_window_end,
            )
            for item in scenario.orders
        ]
        input_trucks = [
            schemas.TruckInput(
                truck_id=item.truck_id,
                no_polisi=item.no_polisi,
                truck_type=item.truck_type,
                truck_category=item.truck_category,
                capacity_kl=item.capacity_kl,
                fixed_cost=item.fixed_cost,
                variable_cost_per_km=item.variable_cost_per_km,
                variable_cost_per_minute=item.variable_cost_per_minute,
                start_depot_id=item.start_depot_id,
                end_depot_id=item.end_depot_id,
                shift_start=item.shift_start,
                shift_end=item.shift_end,
                compatible_product_types=item.compatible_product_types,
                compartments=[
                    schemas.TruckCompartment.model_validate(compartment)
                    for compartment in (item.compartments or [])
                ],
                status=item.status,
                not_available_from=item.not_available_from,
                not_available_to=item.not_available_to,
            )
            for item in scenario.trucks
        ]
        total_penalty = self._calculate_detail_penalty(
            config=objective_config,
            routes=route_details,
            unserved_orders=unserved_orders,
            input_orders=input_orders,
            input_trucks=input_trucks,
            depot_operation_window_start=depot_operation_window_start,
            depot_operation_window_end=depot_operation_window_end,
        )
        total_depot_operation_time_minutes, depot_operation_start, depot_operation_end = (
            self._calculate_depot_operation_window(route_details)
        )

        return schemas.ScenarioDetailResponse(
            scenario_id=UUID(scenario.id),
            dispatch_date=scenario.dispatch_date,
            depot_id=scenario.depot_id,
            depot_service_time_minutes=depot_service_time_minutes,
            status=result.status,
            message=result.message,
            total_orders=result.total_orders,
            total_demand=result.total_demand,
            total_delivered_demand=result.total_delivered_demand,
            total_unserved_orders=result.total_unserved_orders,
            active_truck_count=result.active_truck_count,
            active_truck_type_summary=[
                schemas.TruckTypeSummary.model_validate(item) for item in result.active_truck_type_summary
            ],
            total_distance=result.total_distance,
            total_time=result.total_time,
            total_cost=result.total_cost,
            total_penalty=total_penalty,
            total_depot_operation_time_minutes=total_depot_operation_time_minutes,
            depot_operation_start=depot_operation_start,
            depot_operation_end=depot_operation_end,
            solver_runtime_seconds=result.solver_runtime_seconds,
            objective_config=objective_config,
            route_details=route_details,
            unserved_orders=unserved_orders,
            preprocessing_notes=[
                schemas.PreprocessingNote.model_validate(item) for item in result.preprocessing_notes
            ],
            input_orders=input_orders,
            input_trucks=input_trucks,
            created_at=scenario.created_at,
        )
