"""Map RouteFinder routes to OR-Tools warm-start node routes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.schemas.routefinder_schema import RouteFinderGenerateResponse
from app.services.preprocessing_service import PreprocessedProblem, RouteNode


@dataclass
class MappedInitialSolution:
    routes: list[list[int]]
    warnings: list[str]


class InitialSolutionMapper:
    """Translate canonical RouteFinder sequences into OR-Tools node ids."""

    def map_to_ortools_routes(
        self,
        problem: PreprocessedProblem,
        response: RouteFinderGenerateResponse,
    ) -> MappedInitialSolution:
        vehicle_index_by_id = {truck.truck_id: index for index, truck in enumerate(problem.trucks)}
        shipments_by_spbu: dict[str, list[RouteNode]] = defaultdict(list)
        for shipment in sorted(problem.shipments, key=lambda item: (item.parent_order_id, item.order_id, item.node_index)):
            shipments_by_spbu[shipment.spbu_id].append(shipment)
        reload_nodes_by_vehicle: dict[int, list[RouteNode]] = defaultdict(list)
        for reload_node in sorted(problem.reload_nodes, key=lambda item: item.node_index):
            for vehicle_index in reload_node.allowed_vehicle_indices:
                reload_nodes_by_vehicle[vehicle_index].append(reload_node)

        assigned_nodes: set[int] = set()
        routes: list[list[int]] = [[] for _ in problem.trucks]
        vehicle_trip_loads = [0.0 for _ in problem.trucks]
        warnings: list[str] = []

        for route in response.initial_routes:
            if route.vehicle_id not in vehicle_index_by_id:
                raise ValueError(f"RouteFinder returned unknown vehicle_id {route.vehicle_id}.")
            vehicle_index = vehicle_index_by_id[route.vehicle_id]
            for node_id in route.node_sequence:
                if node_id in {"DEPOT", problem.depot_id}:
                    continue
                compatible_shipments = [
                    shipment
                    for shipment in shipments_by_spbu.get(node_id, [])
                    if shipment.node_index not in assigned_nodes and vehicle_index in shipment.allowed_vehicle_indices
                ]
                if not compatible_shipments:
                    warnings.append(
                        f"No compatible OR-Tools shipment found for node {node_id} on vehicle {route.vehicle_id}."
                    )
                    continue
                shipment = compatible_shipments[0]
                truck = problem.trucks[vehicle_index]
                if vehicle_trip_loads[vehicle_index] + shipment.demand_kl > truck.capacity_kl:
                    reload_pool = reload_nodes_by_vehicle.get(vehicle_index, [])
                    if reload_pool:
                        reload_node = reload_pool.pop(0)
                        routes[vehicle_index].append(reload_node.node_index)
                        vehicle_trip_loads[vehicle_index] = 0.0
                    else:
                        warnings.append(
                            f"Vehicle {route.vehicle_id} has no reload slot left for node {shipment.order_id}."
                        )
                        continue
                routes[vehicle_index].append(shipment.node_index)
                assigned_nodes.add(shipment.node_index)
                vehicle_trip_loads[vehicle_index] += shipment.demand_kl

        return MappedInitialSolution(routes=routes, warnings=warnings)
