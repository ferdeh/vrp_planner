"""Map solver outputs into API responses."""

from __future__ import annotations

from collections import Counter, defaultdict
from uuid import UUID

from ortools.constraint_solver import routing_enums_pb2

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

    def _route_has_delivery(self, route: schemas.RouteDetailResponse) -> bool:
        return any(stop.stop_kind == "delivery" for stop in route.stops) or route.total_load > 0

    def _build_persisted_leg_snapshot(
        self,
        origin_id: str,
        destination_id: str,
        *,
        origin_etd: str | None,
        destination_eta: str | None,
    ) -> dict[str, str | float | None]:
        origin_minutes = hhmm_to_minutes(origin_etd)
        destination_minutes = hhmm_to_minutes(destination_eta)
        travel_minutes = None
        if origin_minutes is not None and destination_minutes is not None:
            travel_minutes = float(max(0, destination_minutes - origin_minutes))
        return {
            "travel_path": f"{origin_id} -> {destination_id}",
            "segment_max_velocity_kmh": "-",
            "travel_distance_km": None,
            "travel_time_minutes": travel_minutes,
        }

    def _build_unserved_constraint_details(
        self,
        reason: str,
        config: schemas.OptimizationConfig,
        order: schemas.OrderInput | None,
    ) -> list[str]:
        details: list[str] = []
        normalized_reason = reason.lower()

        if "time limit" in normalized_reason or "timeout" in normalized_reason:
            details.append(
                f"Solver berhenti di batas waktu {config.solver_options.max_solver_seconds} detik sebelum menemukan solusi feasible."
            )
        elif "solver proved" in normalized_reason or "infeasible" in normalized_reason:
            details.append("Solver menyatakan kombinasi hard constraint pada order ini tidak feasible.")
        elif "solver failed to find a feasible solution" in normalized_reason or "no feasible solution found by solver" in normalized_reason:
            details.append("Solver tidak menemukan kombinasi rute yang memenuhi seluruh hard constraint aktif.")
        elif "dropped by solver with penalty" in normalized_reason:
            details.append(
                f"Allow unserved aktif, jadi solver boleh menjatuhkan order ini dengan penalty {int(config.penalties.unserved_order_penalty)}."
            )

        if "truck category" in normalized_reason:
            details.append("Truck category hard aktif dan tidak ada armada yang memenuhi akses SPBU ini.")
        if "split is disabled" in normalized_reason or "no split" in normalized_reason:
            details.append("No split order hard aktif, jadi demand order ini tidak boleh dipecah.")
        if "compartment" in normalized_reason or "capacity" in normalized_reason:
            details.append("Capacity atau compartment hard aktif dan kapasitas armada tidak cukup untuk shipment ini.")

        if order is not None and order.priority and config.hard_constraints.priority_eta and order.eta:
            details.append(f"SPBU Priority hard aktif, jadi order priority wajib tiba paling lambat {order.eta}.")
        if order is not None and config.hard_constraints.time_window:
            details.append(
                f"Time window SPBU hard aktif, jadi kedatangan wajib berada di {order.time_window_start}-{order.time_window_end}."
            )
        if order is not None and config.hard_constraints.truck_category:
            details.append("Truck category hard aktif membatasi pilihan armada untuk SPBU ini.")
        if not config.soft_constraints.allow_unserved_orders and "solver" in normalized_reason:
            details.append("Allow unserved nonaktif, jadi solver harus menemukan solusi penuh untuk seluruh order.")

        unique_details: list[str] = []
        for item in details:
            if item not in unique_details:
                unique_details.append(item)
        return unique_details

    def _calculate_cost_breakdown(
        self,
        config: schemas.OptimizationConfig,
        routes: list[schemas.RouteDetailResponse],
        unserved_orders: list[schemas.UnservedOrderDetail],
        input_orders: list[schemas.OrderInput],
        input_trucks: list[schemas.TruckInput],
        total_depot_operation_time_minutes: int,
        depot_operation_window_start: str | None = None,
        depot_operation_window_end: str | None = None,
    ) -> schemas.CostBreakdown:
        order_by_id = {item.order_id: item for item in input_orders}
        truck_by_id = {item.truck_id: item for item in input_trucks}
        active_routes = [route for route in routes if self._route_has_delivery(route)]
        activation_cost_total = (
            len(active_routes) * config.penalties.activation_cost_vehicle
            if config.minimize_truck_count
            else 0.0
        )
        distance_cost_total = (
            sum(route.route_distance for route in active_routes) * config.penalties.distance_weight
            if config.minimize_distance
            else 0.0
        )
        time_cost_total = (
            sum(route.route_time for route in active_routes) * config.penalties.time_weight
            if config.minimize_time
            else 0.0
        )
        depot_operation_cost_total = (
            total_depot_operation_time_minutes * config.penalties.depot_operation_time_weight
            if config.minimize_depot_operation_time
            else 0.0
        )

        unserved_penalty_total = 0.0
        late_arrival_penalty_total = 0.0
        priority_eta_penalty_total = 0.0
        overtime_penalty_total = 0.0
        max_total_distance_penalty_total = 0.0
        depot_operation_window_penalty_total = 0.0

        if config.soft_constraints.allow_unserved_orders:
            unserved_penalty_total += len(unserved_orders) * config.penalties.unserved_order_penalty

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
                    late_arrival_penalty_total += (
                        max(0, eta_minutes - window_end_minutes)
                        * config.penalties.late_arrival_penalty_per_minute
                    )

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
                    priority_eta_penalty_total += (
                        max(0, eta_minutes - priority_eta_minutes)
                        * config.penalties.priority_eta_penalty_per_minute
                    )

        if config.soft_constraints.allow_overtime or config.soft_constraints.max_vehicle_working_time or config.soft_constraints.max_route_duration:
            for route in routes:
                truck = truck_by_id.get(route.truck_id)
                if truck is None or not truck.shift_end or not truck.shift_start or not route.return_eta:
                    continue
                return_minutes = hhmm_to_minutes(route.return_eta)
                shift_start_minutes = hhmm_to_minutes(truck.shift_start)
                shift_end_minutes = hhmm_to_minutes(truck.shift_end)
                if return_minutes is None or shift_start_minutes is None or shift_end_minutes is None:
                    continue
                if config.soft_constraints.allow_overtime or config.soft_constraints.max_vehicle_working_time:
                    working_time_limit = (
                        shift_end_minutes
                        if not config.max_vehicle_working_time_minutes
                        else min(shift_end_minutes, shift_start_minutes + config.max_vehicle_working_time_minutes)
                    )
                    overtime_penalty_total += (
                        max(0, return_minutes - working_time_limit)
                        * config.penalties.overtime_penalty_per_minute
                    )
                if config.soft_constraints.max_route_duration and config.max_route_duration_minutes:
                    overtime_penalty_total += (
                        max(0, route.route_time - config.max_route_duration_minutes)
                        * config.penalties.overtime_penalty_per_minute
                    )

        if config.soft_constraints.max_total_distance_per_vehicle and config.max_total_distance_per_vehicle_km:
            for route in routes:
                max_total_distance_penalty_total += (
                    max(0, route.route_distance - config.max_total_distance_per_vehicle_km)
                    * config.penalties.distance_weight
                )

        if config.soft_constraints.depot_operation_window and depot_operation_window_start and depot_operation_window_end:
            _, operation_start, operation_end = self._calculate_depot_operation_window(routes)
            if operation_start and operation_end:
                depot_operation_window_penalty_total += self._calculate_depot_operation_window_penalty(
                    operation_start=operation_start,
                    operation_end=operation_end,
                    window_start=depot_operation_window_start,
                    window_end=depot_operation_window_end,
                    penalty_per_minute=config.penalties.depot_operation_window_penalty_per_minute,
                )

        total_penalty = (
            unserved_penalty_total
            + late_arrival_penalty_total
            + priority_eta_penalty_total
            + overtime_penalty_total
            + max_total_distance_penalty_total
            + depot_operation_window_penalty_total
        )
        total_cost = (
            activation_cost_total
            + distance_cost_total
            + time_cost_total
            + depot_operation_cost_total
            + total_penalty
        )

        return schemas.CostBreakdown(
            activation_cost_total=round(activation_cost_total, 2),
            distance_cost_total=round(distance_cost_total, 2),
            time_cost_total=round(time_cost_total, 2),
            depot_operation_cost_total=round(depot_operation_cost_total, 2),
            late_arrival_penalty_total=round(late_arrival_penalty_total, 2),
            priority_eta_penalty_total=round(priority_eta_penalty_total, 2),
            overtime_penalty_total=round(overtime_penalty_total, 2),
            max_total_distance_penalty_total=round(max_total_distance_penalty_total, 2),
            unserved_penalty_total=round(unserved_penalty_total, 2),
            depot_operation_window_penalty_total=round(depot_operation_window_penalty_total, 2),
            total_penalty_cost=round(total_penalty, 2),
            total_cost=round(total_cost, 2),
        )

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

    def _make_depot_wait_stop(
        self,
        *,
        base_stop: schemas.RouteStopResponse,
        order_id: str,
        eta: str,
        etd: str,
    ) -> schemas.RouteStopResponse:
        return base_stop.model_copy(
            update={
                "order_id": order_id,
                "stop_kind": "depot_wait",
                "travel_path": "",
                "segment_max_velocity_kmh": "-",
                "travel_distance_km": None,
                "travel_time_minutes": None,
                "eta": eta,
                "etd": etd,
                "delivered_volume": 0.0,
                "arrival_status": "waiting_at_depot",
            }
        )

    def _normalize_route_stops(
        self,
        stops: list[schemas.RouteStopResponse],
    ) -> tuple[list[schemas.RouteStopResponse], int]:
        normalized: list[schemas.RouteStopResponse] = []
        index = 0
        reload_sequence = 0
        wait_sequence = 0

        while index < len(stops):
            stop = stops[index]
            if stop.stop_kind != "depot_reload":
                normalized.append(stop)
                index += 1
                continue

            block_end = index
            while block_end < len(stops) and stops[block_end].stop_kind == "depot_reload":
                block_end += 1
            block = stops[index:block_end]

            previous_stop = normalized[-1] if normalized else None
            next_stop = stops[block_end] if block_end < len(stops) else None
            has_previous_delivery = previous_stop is not None and previous_stop.stop_kind == "delivery"
            has_next_delivery = next_stop is not None and next_stop.stop_kind == "delivery"

            if len(block) == 1:
                if has_previous_delivery and has_next_delivery:
                    reload_sequence += 1
                    normalized.append(
                        block[0].model_copy(
                            update={
                                "order_id": f"DEPOT_RELOAD#{reload_sequence}",
                                "arrival_status": "reloaded_at_depot",
                            }
                        )
                    )
                else:
                    wait_sequence += 1
                    normalized.append(
                        self._make_depot_wait_stop(
                            base_stop=block[0],
                            order_id=f"DEPOT_WAIT#{wait_sequence}",
                            eta=block[0].eta,
                            etd=block[0].etd,
                        )
                    )
            else:
                if has_previous_delivery and has_next_delivery:
                    reload_sequence += 1
                    normalized.append(
                        block[0].model_copy(
                            update={
                                "order_id": f"DEPOT_RELOAD#{reload_sequence}",
                                "arrival_status": "reloaded_at_depot",
                            }
                        )
                    )
                    wait_sequence += 1
                    normalized.append(
                        self._make_depot_wait_stop(
                            base_stop=block[1],
                            order_id=f"DEPOT_WAIT#{wait_sequence}",
                            eta=block[1].eta,
                            etd=block[-1].etd,
                        )
                    )
                else:
                    wait_sequence += 1
                    normalized.append(
                        self._make_depot_wait_stop(
                            base_stop=block[0],
                            order_id=f"DEPOT_WAIT#{wait_sequence}",
                            eta=block[0].eta,
                            etd=block[-1].etd,
                        )
                    )

            index = block_end

        trip_sequence = 1
        resequenced: list[schemas.RouteStopResponse] = []
        for sequence, stop in enumerate(normalized, start=1):
            if stop.stop_kind == "depot_reload":
                trip_sequence += 1
            resequenced.append(
                stop.model_copy(
                    update={
                        "sequence": sequence,
                        "trip_sequence": trip_sequence,
                    }
                )
            )
        return resequenced, trip_sequence

    def _calculate_depot_operation_window(
        self,
        routes: list[schemas.RouteDetailResponse],
    ) -> tuple[int, str | None, str | None]:
        """Return depot active span from first depot activity until last gate-out.

        This intentionally ignores truck return-to-depot time. The end of depot
        operation is the latest departure (`etd`) from the depot, whether from
        initial loading, depot wait, or reload.
        """

        depot_activity_windows: list[tuple[int, int]] = []

        for route in routes:
            if route.origin_service_start and route.origin_etd:
                depot_activity_windows.append(
                    (
                        hhmm_to_minutes(route.origin_service_start),
                        hhmm_to_minutes(route.origin_etd),
                    )
                )
            for stop in route.stops:
                if stop.stop_kind not in {"depot_reload", "depot_wait"}:
                    continue
                depot_activity_windows.append((hhmm_to_minutes(stop.eta), hhmm_to_minutes(stop.etd)))

        if not depot_activity_windows:
            return 0, None, None

        start_minute = min(start for start, _ in depot_activity_windows)
        end_minute = max(end for _, end in depot_activity_windows)
        return end_minute - start_minute, minutes_to_hhmm(start_minute), minutes_to_hhmm(end_minute)

    def _build_persisted_route_details(
        self,
        scenario,
        *,
        depot_name: str,
        depot_gate_limit: int | None,
        depot_service_time_minutes: int,
        spbu_name_by_id: dict[str, str],
        truck_no_polisi_by_id: dict[str, str | None],
        include_stops: bool,
    ) -> list[schemas.RouteDetailResponse]:
        route_details: list[schemas.RouteDetailResponse] = []

        for route in scenario.result.routes:
            return_eta = self._derive_return_eta(
                self._derive_origin_service_start(route.origin_etd, depot_service_time_minutes),
                route.route_time,
            )

            if include_stops:
                ordered_stops = sorted(route.stops, key=lambda item: item.sequence)
                enriched_stops: list[schemas.RouteStopResponse] = []
                previous_node_name = scenario.depot_id
                previous_etd = route.origin_etd
                for stop in ordered_stops:
                    if stop.order_id.startswith("DEPOT_WAIT#"):
                        stop_kind = "depot_wait"
                    elif stop.order_id.startswith("DEPOT_RELOAD#"):
                        stop_kind = "depot_reload"
                    else:
                        stop_kind = "delivery"
                    if stop_kind == "depot_wait":
                        leg_snapshot = {
                            "travel_path": "",
                            "segment_max_velocity_kmh": "-",
                            "travel_distance_km": None,
                            "travel_time_minutes": None,
                        }
                    else:
                        leg_snapshot = self._build_persisted_leg_snapshot(
                            previous_node_name,
                            stop.spbu_id,
                            origin_etd=previous_etd,
                            destination_eta=stop.eta,
                        )
                    enriched_stops.append(
                        schemas.RouteStopResponse(
                            sequence=stop.sequence,
                            order_id=stop.order_id,
                            parent_order_id=stop.parent_order_id,
                            spbu_id=stop.spbu_id,
                            stop_kind=stop_kind,
                            trip_sequence=1,
                            spbu_name=depot_name if stop_kind in {"depot_reload", "depot_wait"} else spbu_name_by_id.get(stop.spbu_id),
                            travel_path=str(leg_snapshot.get("travel_path") or ""),
                            segment_max_velocity_kmh=str(leg_snapshot.get("segment_max_velocity_kmh") or "-"),
                            travel_distance_km=float(leg_snapshot["travel_distance_km"]) if leg_snapshot.get("travel_distance_km") is not None else None,
                            travel_time_minutes=float(leg_snapshot["travel_time_minutes"]) if leg_snapshot.get("travel_time_minutes") is not None else None,
                            eta=stop.eta,
                            etd=stop.etd,
                            delivered_volume=stop.delivered_volume,
                            arrival_status=stop.arrival_status,
                        )
                    )
                    previous_node_name = stop.spbu_id
                    previous_etd = stop.etd

                enriched_stops, trip_count = self._normalize_route_stops(enriched_stops)
                return_leg = (
                    self._build_persisted_leg_snapshot(
                        enriched_stops[-1].spbu_id,
                        scenario.depot_id,
                        origin_etd=enriched_stops[-1].etd,
                        destination_eta=return_eta,
                    )
                    if enriched_stops
                    else {
                        "travel_path": "",
                        "segment_max_velocity_kmh": "-",
                        "travel_distance_km": None,
                        "travel_time_minutes": None,
                    }
                )
            else:
                enriched_stops = []
                trip_count = 1
                return_leg = {
                    "travel_path": "",
                    "segment_max_velocity_kmh": "-",
                    "travel_distance_km": None,
                    "travel_time_minutes": None,
                }

            route_details.append(
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
                    return_eta=return_eta,
                    return_path=str(return_leg.get("travel_path") or ""),
                    return_segment_max_velocity_kmh=str(return_leg.get("segment_max_velocity_kmh") or "-"),
                    return_distance_km=float(return_leg["travel_distance_km"]) if return_leg.get("travel_distance_km") is not None else None,
                    return_travel_time_minutes=float(return_leg["travel_time_minutes"]) if return_leg.get("travel_time_minutes") is not None else None,
                    truck_type=route.truck_type,
                    capacity_kl=route.capacity_kl,
                    total_load=route.total_load,
                    utilization_percent=route.utilization_percent,
                    route_distance=route.route_distance,
                    route_time=route.route_time,
                    stop_count=route.stop_count if not include_stops else len(enriched_stops),
                    trip_count=trip_count,
                    stops=enriched_stops,
                )
            )

        return route_details

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
                            if problem.config.soft_constraints.time_window:
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
                    stops, trip_sequence = self._normalize_route_stops(stops)
                    has_delivery = any(stop.stop_kind == "delivery" for stop in stops)
                    end_time = assignment.Value(time_dimension.CumulVar(routing.End(vehicle_id)))
                    start_time = assignment.Value(time_dimension.CumulVar(routing.Start(vehicle_id)))
                    route_time = max(0, end_time - start_time) + problem.depot_service_time_minutes
                    route_distance = assignment.Value(distance_dimension.CumulVar(routing.End(vehicle_id)))
                    return_leg_audit = self._get_leg_audit_safe(stops[-1].spbu_id, problem.depot_id)
                    route_detail = schemas.RouteDetailResponse(
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
                    route_details.append(route_detail)
                    if has_delivery:
                        total_distance += route_distance
                        total_time += route_time
                        active_types[truck.truck_type] += 1
                        active_capacity_by_type[truck.truck_type] += truck.capacity_kl

        order_by_id = {item.order_id: item for item in problem.orders}
        unserved = [
            item.model_copy(
                update={
                    "constraint_details": self._build_unserved_constraint_details(
                        reason=item.reason,
                        config=problem.config,
                        order=order_by_id.get(item.parent_order_id) or order_by_id.get(item.order_id),
                    )
                }
            )
            for item in problem.preassigned_unserved
        ]
        dropped_penalty = 0.0
        for shipment in problem.shipments:
            if shipment.order_id not in visited_orders:
                order = order_by_id.get(shipment.parent_order_id) or order_by_id.get(shipment.order_id)
                reason = "Dropped by solver with penalty." if assignment else solver_output.message
                unserved.append(
                    schemas.UnservedOrderDetail(
                        order_id=shipment.order_id,
                        parent_order_id=shipment.parent_order_id,
                        spbu_id=shipment.spbu_id,
                        demand_kl=shipment.demand_kl,
                        reason=reason,
                        constraint_details=self._build_unserved_constraint_details(
                            reason=reason,
                            config=problem.config,
                            order=order,
                        ),
                    )
                )
                if problem.config.soft_constraints.allow_unserved_orders:
                    dropped_penalty += problem.config.penalties.unserved_order_penalty

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
        cost_breakdown = self._calculate_cost_breakdown(
            config=problem.config,
            routes=route_details,
            unserved_orders=unserved,
            input_orders=problem.orders,
            input_trucks=problem.trucks,
            total_depot_operation_time_minutes=total_depot_operation_time_minutes,
            depot_operation_window_start=minutes_to_hhmm(problem.depot_operation_window_start),
            depot_operation_window_end=minutes_to_hhmm(problem.depot_operation_window_end),
        )
        if assignment is None:
            if solver_output.search_status == routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT:
                status: schemas.SolutionStatus = "timeout"
            else:
                status = "infeasible"
        elif served_all:
            status = "feasible"
        else:
            status = "partial"

        return schemas.OptimizationResultResponse(
            scenario_id=UUID(str(scenario_id)),
            status=status,
            message=solver_output.message,
            total_orders=len(problem.orders),
            total_demand=problem.total_demand,
            total_delivered_demand=round(delivered_demand, 2),
            total_unserved_orders=len({item.parent_order_id for item in unserved}),
            active_truck_count=sum(1 for route in route_details if self._route_has_delivery(route)),
            active_truck_type_summary=active_summary,
            total_distance=round(total_distance, 2),
            total_time=round(total_time, 2),
            total_cost=cost_breakdown.total_cost,
            total_penalty=cost_breakdown.total_penalty_cost,
            cost_breakdown=cost_breakdown,
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
        *,
        include_route_stops: bool = True,
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
        scenario_spbu_ids = {item.spbu_id for item in scenario.orders}
        route_stop_spbu_ids = {stop.spbu_id for route in result.routes for stop in route.stops}
        try:
            spbu_name_by_id = {
                spbu_id: item.name
                for spbu_id, item in self.master_data_client.get_spbu_many(
                    list(route_stop_spbu_ids | scenario_spbu_ids),
                    depot_id=scenario.depot_id,
                ).items()
            }
        except Exception:
            spbu_name_by_id = {}
        objective_config = schemas.OptimizationConfig.model_validate(
            scenario.optimization_config.config_snapshot
        )
        depot_service_time_minutes = int(scenario.raw_request.get("depot_service_time_minutes") or 0)
        metric_route_details = self._build_persisted_route_details(
            scenario,
            depot_name=depot_name,
            depot_gate_limit=depot_gate_limit,
            depot_service_time_minutes=depot_service_time_minutes,
            spbu_name_by_id=spbu_name_by_id,
            truck_no_polisi_by_id=truck_no_polisi_by_id,
            include_stops=True,
        )
        route_details = (
            metric_route_details
            if include_route_stops
            else self._build_persisted_route_details(
                scenario,
                depot_name=depot_name,
                depot_gate_limit=depot_gate_limit,
                depot_service_time_minutes=depot_service_time_minutes,
                spbu_name_by_id=spbu_name_by_id,
                truck_no_polisi_by_id=truck_no_polisi_by_id,
                include_stops=False,
            )
        )
        input_orders = [
            schemas.OrderInput(
                order_id=item.order_id,
                spbu_id=item.spbu_id,
                spbu_name=spbu_name_by_id.get(item.spbu_id),
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
        input_order_by_id = {item.order_id: item for item in input_orders}
        unserved_orders = [
            schemas.UnservedOrderDetail(
                order_id=item.order_id,
                parent_order_id=item.parent_order_id,
                spbu_id=item.spbu_id,
                demand_kl=item.demand_kl,
                reason=item.reason,
                constraint_details=self._build_unserved_constraint_details(
                    reason=item.reason,
                    config=objective_config,
                    order=input_order_by_id.get(item.parent_order_id) or input_order_by_id.get(item.order_id),
                ),
            )
            for item in result.unserved_orders
        ]
        input_trucks = [
            schemas.TruckInput(
                truck_id=item.truck_id,
                no_polisi=item.no_polisi,
                truck_type=item.truck_type,
                truck_category=item.truck_category,
                capacity_kl=item.capacity_kl,
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
        total_depot_operation_time_minutes, depot_operation_start, depot_operation_end = (
            self._calculate_depot_operation_window(metric_route_details)
        )
        cost_breakdown = self._calculate_cost_breakdown(
            config=objective_config,
            routes=metric_route_details,
            unserved_orders=unserved_orders,
            input_orders=input_orders,
            input_trucks=input_trucks,
            total_depot_operation_time_minutes=total_depot_operation_time_minutes,
            depot_operation_window_start=depot_operation_window_start,
            depot_operation_window_end=depot_operation_window_end,
        )
        active_metric_routes = [route for route in metric_route_details if self._route_has_delivery(route)]
        active_type_counter: Counter[str] = Counter(route.truck_type for route in active_metric_routes)
        active_capacity_by_type: defaultdict[str, float] = defaultdict(float)
        for route in active_metric_routes:
            active_capacity_by_type[route.truck_type] += route.capacity_kl

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
            active_truck_count=len(active_metric_routes),
            active_truck_type_summary=[
                schemas.TruckTypeSummary(
                    truck_type=truck_type,
                    active_count=count,
                    total_capacity_kl=round(active_capacity_by_type[truck_type], 2),
                )
                for truck_type, count in sorted(active_type_counter.items())
            ],
            total_distance=result.total_distance,
            total_time=result.total_time,
            total_cost=cost_breakdown.total_cost,
            total_penalty=cost_breakdown.total_penalty_cost,
            cost_breakdown=cost_breakdown,
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
