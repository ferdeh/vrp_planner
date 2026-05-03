"""Placeholder RouteFinder heuristic implementation."""

from __future__ import annotations

from collections import defaultdict

from app.schemas.canonical_vrp_schema import CanonicalVRPModel
from app.schemas.routefinder_schema import (
    RouteFinderGenerateResponse,
    RouteFinderInitialRoute,
    RouteFinderScore,
)


class RouteFinderHeuristicStub:
    """Simple nearest-neighbor style seeding for future RouteFinder replacement."""

    def generate_initial_solution(self, model: CanonicalVRPModel) -> RouteFinderGenerateResponse:
        if not model.orders or not model.vehicles:
            return RouteFinderGenerateResponse(
                status="FAILED",
                initial_routes=[],
                warnings=["Canonical VRP model does not contain orders or vehicles."],
            )

        route_by_vehicle: dict[str, list[str]] = {}
        vehicle_loads: dict[str, float] = {vehicle.vehicle_id: 0.0 for vehicle in model.vehicles}
        orders_by_vehicle: dict[str, list[str]] = defaultdict(list)

        for order in sorted(model.orders, key=lambda item: (item.priority is False, item.quantity_kl, item.order_id)):
            assigned_vehicle = None
            for vehicle in model.vehicles:
                if not vehicle.is_available:
                    continue
                if vehicle.truck_category is not None and order.allowed_truck_categories:
                    if vehicle.truck_category not in order.allowed_truck_categories:
                        continue
                if order.product_code not in vehicle.compatible_product_codes:
                    continue
                if (
                    order.supply_depot_compatibility
                    and vehicle.depot_id not in order.supply_depot_compatibility
                ):
                    continue
                if vehicle_loads[vehicle.vehicle_id] + order.quantity_kl > vehicle.capacity_kl:
                    continue
                assigned_vehicle = vehicle
                break

            if assigned_vehicle is None:
                return RouteFinderGenerateResponse(
                    status="FAILED",
                    initial_routes=[],
                    warnings=[f"Unable to build stub initial route for order {order.order_id}."],
                )

            vehicle_loads[assigned_vehicle.vehicle_id] += order.quantity_kl
            orders_by_vehicle[assigned_vehicle.vehicle_id].append(order.node_id)

        for vehicle in model.vehicles:
            sequence = [vehicle.depot_id, *orders_by_vehicle.get(vehicle.vehicle_id, []), vehicle.end_depot_id]
            route_by_vehicle[vehicle.vehicle_id] = sequence

        estimated_distance = 0.0
        estimated_duration = 0.0
        for sequence in route_by_vehicle.values():
            if len(sequence) <= 2:
                continue
            estimated_distance += max(0, len(sequence) - 2) * 10
            estimated_duration += max(0, len(sequence) - 2) * 30

        active_vehicle_count = sum(1 for sequence in route_by_vehicle.values() if len(sequence) > 2)
        utilization = 0.0
        if active_vehicle_count:
            utilization = sum(
                vehicle_loads[vehicle.vehicle_id] / max(1.0, next(v.capacity_kl for v in model.vehicles if v.vehicle_id == vehicle.vehicle_id))
                for vehicle in model.vehicles
                if len(route_by_vehicle[vehicle.vehicle_id]) > 2
            ) / active_vehicle_count

        return RouteFinderGenerateResponse(
            status="SUCCESS",
            initial_routes=[
                RouteFinderInitialRoute(vehicle_id=vehicle_id, node_sequence=sequence)
                for vehicle_id, sequence in route_by_vehicle.items()
            ],
            score=RouteFinderScore(
                estimated_distance=round(estimated_distance, 2),
                estimated_duration=round(estimated_duration, 2),
                estimated_utilization=round(utilization, 4),
            ),
            warnings=["Using routefinder_heuristic_stub placeholder implementation."],
        )
