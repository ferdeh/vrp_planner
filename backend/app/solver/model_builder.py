"""Build OR-Tools routing model from preprocessed problem."""

from __future__ import annotations

from dataclasses import dataclass

from ortools.constraint_solver import pywrapcp

from app.models import schemas
from app.services.preprocessing_service import PreprocessedProblem
from app.solver.constraints import (
    TimeConstraintArtifacts,
    apply_capacity_constraints,
    apply_distance_constraints,
    apply_optional_visits,
    apply_time_constraints,
    apply_vehicle_compatibility,
)
from app.solver.objective import transit_cost, vehicle_fixed_cost


@dataclass
class BuiltModel:
    manager: pywrapcp.RoutingIndexManager
    routing: pywrapcp.RoutingModel
    time_dimension: pywrapcp.RoutingDimension
    distance_dimension: pywrapcp.RoutingDimension
    capacity_dimension: pywrapcp.RoutingDimension
    extra_objective_vars: list[pywrapcp.IntVar]
    extra_objective_weights: list[int]


def build_routing_model(problem: PreprocessedProblem) -> BuiltModel:
    """Build routing model and all configured dimensions."""
    return build_routing_model_with_options(problem)


def build_routing_model_with_options(
    problem: PreprocessedProblem,
    *,
    include_soft_priority_eta_objective: bool = True,
) -> BuiltModel:
    """Build routing model with optional objective toggles for multi-pass solving."""

    manager = pywrapcp.RoutingIndexManager(len(problem.route_nodes) + 1, len(problem.trucks), 0)
    routing = pywrapcp.RoutingModel(manager)

    for vehicle_id, truck in enumerate(problem.trucks):
        def vehicle_cost(from_index: int, to_index: int, vehicle_id: int = vehicle_id) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            from_detail = problem.get_node(from_node)
            to_detail = problem.get_node(to_node)
            from_name = "DEPOT" if from_detail is None else from_detail.matrix_node_name
            to_name = "DEPOT" if to_detail is None else to_detail.matrix_node_name
            distance = problem.distance_matrix[problem.matrix_positions[from_name]][problem.matrix_positions[to_name]]
            travel_time = problem.time_matrix[problem.matrix_positions[from_name]][problem.matrix_positions[to_name]]
            return transit_cost(
                distance,
                travel_time,
                problem.trucks[vehicle_id],
                problem.config,
            )

        callback_index = routing.RegisterTransitCallback(vehicle_cost)
        routing.SetArcCostEvaluatorOfVehicle(callback_index, vehicle_id)
        routing.SetFixedCostOfVehicle(vehicle_fixed_cost(truck, problem.config), vehicle_id)

    capacity_dimension = apply_capacity_constraints(routing, manager, problem)
    distance_dimension = apply_distance_constraints(routing, manager, problem)
    time_artifacts: TimeConstraintArtifacts = apply_time_constraints(
        routing,
        manager,
        problem,
        include_soft_priority_eta_objective=include_soft_priority_eta_objective,
    )
    time_dimension = time_artifacts.dimension
    apply_vehicle_compatibility(routing, manager, problem)
    apply_optional_visits(routing, manager, problem)

    return BuiltModel(
        manager=manager,
        routing=routing,
        time_dimension=time_dimension,
        distance_dimension=distance_dimension,
        capacity_dimension=capacity_dimension,
        extra_objective_vars=time_artifacts.extra_objective_vars,
        extra_objective_weights=time_artifacts.extra_objective_weights,
    )
