"""Final solution validator used as the last solver gate."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from app.models import schemas as legacy_schemas
from app.schemas.solution_schema import FinalSolutionValidationResult
from app.services.preprocessing_service import PreprocessedProblem
from app.utils.time_utils import hhmm_to_minutes


class SolutionValidator:
    """Check high-signal hard constraints on the final solver result."""

    def validate(
        self,
        *,
        payload: legacy_schemas.OptimizationRequest,
        problem: PreprocessedProblem,
        result: legacy_schemas.OptimizationResultResponse,
    ) -> FinalSolutionValidationResult:
        violations: dict[str, list[object]] = defaultdict(list)
        penalties: dict[str, float] = {}
        truck_by_id = {truck.truck_id: truck for truck in payload.available_trucks}
        order_by_id = {order.order_id: order for order in payload.orders}
        dispatch_date = payload.dispatch_date if isinstance(payload.dispatch_date, date) else date.fromisoformat(str(payload.dispatch_date))

        parent_order_counts: Counter[str] = Counter()
        fulfilled_order_ids: set[str] = set()

        for route in result.route_details:
            truck = truck_by_id.get(route.truck_id)
            if truck is None:
                violations["vehicle_assignment"].append({"truck_id": route.truck_id, "reason": "Unknown vehicle"})
                continue
            if (truck.status or "").lower() in {"inactive", "unavailable"}:
                violations["vehicle_availability"].append({"truck_id": route.truck_id, "reason": "Vehicle marked unavailable"})

            max_compartment = max((item.capacity_kl for item in truck.compartments), default=truck.capacity_kl)
            route_parent_counts: Counter[str] = Counter()
            trip_count = max(1, route.trip_count)
            current_trip_load = 0.0
            if problem.config.max_vehicle_working_time_minutes:
                overtime_minutes = max(0.0, route.route_time - problem.config.max_vehicle_working_time_minutes)
                if overtime_minutes > 1e-6:
                    if problem.config.hard_constraints.max_vehicle_working_time:
                        violations["max_working_minutes"].append(
                            {
                                "truck_id": route.truck_id,
                                "route_time": route.route_time,
                                "max_working_minutes": problem.config.max_vehicle_working_time_minutes,
                            }
                        )
                    elif (
                        problem.config.soft_constraints.allow_overtime
                        or problem.config.soft_constraints.max_vehicle_working_time
                    ):
                        penalties["max_vehicle_working_time"] = penalties.get("max_vehicle_working_time", 0.0) + overtime_minutes
            max_trips = max(1, len(problem.reload_nodes) + 1)
            if trip_count > max_trips:
                violations["max_trips"].append(
                    {"truck_id": route.truck_id, "trip_count": trip_count, "max_trips": max_trips}
                )

            for stop in route.stops:
                if stop.stop_kind == "depot_reload":
                    current_trip_load = 0.0
                    continue
                if stop.stop_kind != "delivery":
                    continue
                route_parent_counts[stop.parent_order_id] += 1
                parent_order_counts[stop.parent_order_id] += 1
                fulfilled_order_ids.add(stop.parent_order_id)
                current_trip_load += stop.delivered_volume
                if current_trip_load - truck.capacity_kl > 1e-6:
                    violations["vehicle_capacity"].append(
                        {"truck_id": route.truck_id, "load": current_trip_load, "capacity_kl": truck.capacity_kl}
                    )
                if stop.delivered_volume - max_compartment > 1e-6:
                    violations["compartment_capacity"].append(
                        {
                            "truck_id": route.truck_id,
                            "order_id": stop.order_id,
                            "delivered_volume": stop.delivered_volume,
                            "max_compartment_kl": max_compartment,
                        }
                    )
                order = order_by_id.get(stop.parent_order_id)
                if order is None:
                    violations["demand_fulfillment"].append({"order_id": stop.parent_order_id, "reason": "Order not found"})
                    continue
                if order.product_type not in truck.compatible_product_types:
                    violations["product_compatibility"].append(
                        {"truck_id": route.truck_id, "order_id": stop.parent_order_id, "product_code": order.product_type}
                    )
                spbu = problem.spbu_map.get(stop.spbu_id)
                if spbu and spbu.truck_category is not None and truck.truck_category is not None:
                    if (
                        problem.config.hard_constraints.truck_category
                        and truck.truck_category > spbu.truck_category
                    ):
                        violations["truck_category"].append(
                            {"truck_id": route.truck_id, "spbu_id": stop.spbu_id, "truck_category": truck.truck_category}
                        )
                if spbu and spbu.supply_depot_ids and truck.start_depot_id not in spbu.supply_depot_ids:
                    violations["supply_depot"].append(
                        {"truck_id": route.truck_id, "spbu_id": stop.spbu_id, "depot_id": truck.start_depot_id}
                    )
                eta_minutes = hhmm_to_minutes(stop.eta)
                tw_end = hhmm_to_minutes(order.time_window_end)
                if eta_minutes is not None and tw_end is not None and eta_minutes > tw_end:
                    if problem.config.hard_constraints.time_window:
                        violations["time_window"].append(
                            {"order_id": stop.parent_order_id, "eta": stop.eta, "time_window_end": order.time_window_end}
                        )
                    elif problem.config.soft_constraints.time_window:
                        penalties["time_window"] = penalties.get("time_window", 0.0) + max(
                            0,
                            eta_minutes - tw_end,
                        )
                if order.priority and order.eta:
                    eta_limit = hhmm_to_minutes(order.eta)
                    if eta_minutes is not None and eta_limit is not None and eta_minutes > eta_limit:
                        if problem.config.hard_constraints.priority_eta:
                            violations["priority_eta"].append(
                                {"order_id": stop.parent_order_id, "eta": stop.eta, "priority_eta": order.eta}
                            )
                        elif problem.config.soft_constraints.priority_eta:
                            penalties["priority_eta"] = penalties.get("priority_eta", 0.0) + max(
                                0,
                                eta_minutes - eta_limit,
                            )

            if problem.config.hard_constraints.no_split_order:
                for parent_order_id, count in route_parent_counts.items():
                    if count > 1:
                        violations["duplicate_customer_visit"].append(
                            {"truck_id": route.truck_id, "order_id": parent_order_id, "visit_count": count}
                        )
            if truck.start_depot_id != payload.depot_id or truck.end_depot_id != payload.depot_id:
                violations["depot_compatibility"].append(
                    {
                        "truck_id": route.truck_id,
                        "start_depot_id": truck.start_depot_id,
                        "end_depot_id": truck.end_depot_id,
                        "expected_depot_id": payload.depot_id,
                    }
                )
            if truck.not_available_from and truck.not_available_to:
                blocked_from = date.fromisoformat(truck.not_available_from)
                blocked_to = date.fromisoformat(truck.not_available_to)
                if blocked_from <= dispatch_date <= blocked_to:
                    violations["vehicle_availability"].append(
                        {"truck_id": route.truck_id, "reason": "Vehicle blocked by availability window"}
                    )

        for order in payload.orders:
            if order.order_id not in fulfilled_order_ids and all(
                item.parent_order_id != order.order_id for item in result.unserved_orders
            ):
                violations["demand_fulfillment"].append(
                    {"order_id": order.order_id, "reason": "Order neither delivered nor marked unserved"}
                )

        is_valid = all(not items for items in violations.values())
        return FinalSolutionValidationResult(
            is_valid=is_valid,
            status="passed" if is_valid else "failed",
            hard_constraint_violations=dict(violations),
            soft_constraint_penalties=penalties,
        )
