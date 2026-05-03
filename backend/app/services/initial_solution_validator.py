"""Validate RouteFinder warm-start routes before OR-Tools consumes them."""

from __future__ import annotations

from app.schemas.solution_schema import InitialSolutionValidationResult
from app.services.preprocessing_service import PreprocessedProblem


class InitialSolutionValidator:
    """Lightweight guardrail for initial routes."""

    def validate(
        self,
        problem: PreprocessedProblem,
        routes: list[list[int]],
    ) -> InitialSolutionValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if len(routes) != len(problem.trucks):
            errors.append("Warm-start route count does not match vehicle count.")
            return InitialSolutionValidationResult(is_valid=False, errors=errors, warnings=warnings)

        shipment_nodes = {shipment.node_index for shipment in problem.shipments}
        seen_shipments: set[int] = set()

        for vehicle_index, route in enumerate(routes):
            truck = problem.trucks[vehicle_index]
            current_load = 0.0
            for node_index in route:
                node = problem.get_node(node_index)
                if node is None:
                    errors.append(f"Route for vehicle {truck.truck_id} references unknown node {node_index}.")
                    continue
                if vehicle_index not in node.allowed_vehicle_indices:
                    errors.append(f"Node {node.order_id} is not compatible with vehicle {truck.truck_id}.")
                if node.node_kind == "reload":
                    current_load = 0.0
                    continue
                if node.node_index in seen_shipments:
                    errors.append(f"Shipment {node.order_id} is duplicated in warm-start routes.")
                    continue
                seen_shipments.add(node.node_index)
                current_load += node.demand_kl
                if current_load - truck.capacity_kl > 1e-6:
                    errors.append(f"Vehicle {truck.truck_id} exceeds capacity on warm-start route.")
                if node.product_type not in truck.compatible_product_types:
                    errors.append(f"Vehicle {truck.truck_id} cannot carry product {node.product_type}.")
                spbu = problem.spbu_map.get(node.spbu_id)
                if spbu and spbu.truck_category is not None and truck.truck_category is not None:
                    if truck.truck_category > spbu.truck_category:
                        errors.append(f"Vehicle {truck.truck_id} violates SPBU truck category at {node.spbu_id}.")
                if spbu and spbu.supply_depot_ids and truck.start_depot_id not in spbu.supply_depot_ids:
                    errors.append(f"Vehicle {truck.truck_id} is incompatible with supply depot policy for {node.spbu_id}.")

        missing_shipments = shipment_nodes - seen_shipments
        if missing_shipments:
            warnings.append(f"Warm-start leaves {len(missing_shipments)} shipment nodes unassigned.")

        return InitialSolutionValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
            route_count=len(routes),
            assigned_shipments=len(seen_shipments),
        )
