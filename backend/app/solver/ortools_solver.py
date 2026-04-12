"""OR-Tools routing solver orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.models import schemas
from app.services.preprocessing_service import PreprocessedProblem
from app.solver.model_builder import BuiltModel, build_routing_model_with_options
from app.solver.constraints import VehicleActivationPolicy
from app.utils.time_utils import hhmm_to_minutes

logger = logging.getLogger(__name__)


FIRST_STRATEGIES = {
    "AUTOMATIC": routing_enums_pb2.FirstSolutionStrategy.AUTOMATIC,
    "PATH_CHEAPEST_ARC": routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
    "PARALLEL_CHEAPEST_INSERTION": routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION,
    "LOCAL_CHEAPEST_INSERTION": routing_enums_pb2.FirstSolutionStrategy.LOCAL_CHEAPEST_INSERTION,
}

LOCAL_SEARCH = {
    "AUTOMATIC": routing_enums_pb2.LocalSearchMetaheuristic.AUTOMATIC,
    "GUIDED_LOCAL_SEARCH": routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH,
    "TABU_SEARCH": routing_enums_pb2.LocalSearchMetaheuristic.TABU_SEARCH,
    "SIMULATED_ANNEALING": routing_enums_pb2.LocalSearchMetaheuristic.SIMULATED_ANNEALING,
}


@dataclass
class SolverOutput:
    built_model: BuiltModel
    assignment: pywrapcp.Assignment | None
    runtime_seconds: float
    message: str
    search_status: int


@dataclass
class StageSolveResult:
    built_model: BuiltModel
    assignment: pywrapcp.Assignment | None
    search_status: int


@dataclass(frozen=True)
class VehicleRouteMetric:
    vehicle_index: int
    route_minutes: int
    end_minutes: int
    overtime_minutes: int
    shift_slack_minutes: int


class OrToolsSolver:
    """Solve the prepared routing problem using OR-Tools."""

    @staticmethod
    def _is_heavy_multi_trip_problem(problem: PreprocessedProblem) -> bool:
        if not problem.reload_nodes:
            return False
        initial_capacity = sum(truck.capacity_kl for truck in problem.trucks)
        if problem.total_demand <= initial_capacity:
            return False
        min_reload_nodes = max(3, len(problem.trucks) // 2)
        min_shipments = max(10, len(problem.trucks) * 2)
        return len(problem.reload_nodes) >= min_reload_nodes and len(problem.shipments) >= min_shipments

    @staticmethod
    def _effective_time_limit_seconds(
        problem: PreprocessedProblem,
        requested_seconds: int,
    ) -> int:
        if OrToolsSolver._is_heavy_multi_trip_problem(problem):
            return max(45, requested_seconds)
        return requested_seconds

    @staticmethod
    def _resolve_first_solution_strategy(problem: PreprocessedProblem) -> int:
        requested = problem.config.solver_options.first_solution_strategy
        if requested == "PATH_CHEAPEST_ARC" and problem.reload_nodes:
            # Reload nodes behave like optional insertion points. Arc-cheapest
            # seeding tends to saturate only the initial truck capacity and
            # never activates depot reloads in larger multi-trip scenarios.
            requested = "PARALLEL_CHEAPEST_INSERTION"
        return FIRST_STRATEGIES.get(
            requested,
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
        )

    @staticmethod
    def _build_message(search_status: int, assignment: pywrapcp.Assignment | None) -> str:
        if assignment is not None:
            return "Optimization finished."
        if search_status == routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT:
            return "Solver reached the time limit before finding a feasible solution."
        if search_status == routing_enums_pb2.RoutingSearchStatus.ROUTING_INFEASIBLE:
            return "Solver proved the scenario infeasible under current hard constraints."
        if search_status == routing_enums_pb2.RoutingSearchStatus.ROUTING_INVALID:
            return "Solver rejected the routing model as invalid."
        return "Solver failed to find a feasible solution under current constraints."

    @staticmethod
    def _build_search_parameters(
        problem: PreprocessedProblem,
        *,
        time_limit_seconds: int | None = None,
        local_search_metaheuristic: str | None = None,
    ) -> pywrapcp.DefaultRoutingSearchParameters:
        requested_seconds = int(
            time_limit_seconds
            if time_limit_seconds is not None
            else problem.config.solver_options.max_solver_seconds
        )
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.time_limit.seconds = max(
            1,
            requested_seconds,
        )
        search_parameters.first_solution_strategy = OrToolsSolver._resolve_first_solution_strategy(problem)
        search_parameters.local_search_metaheuristic = LOCAL_SEARCH.get(
            local_search_metaheuristic or problem.config.solver_options.local_search_metaheuristic,
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH,
        )
        search_parameters.log_search = False
        return search_parameters

    @staticmethod
    def _close_model(
        built_model: BuiltModel,
        search_parameters: pywrapcp.DefaultRoutingSearchParameters,
    ) -> None:
        built_model.routing.CloseModelWithParameters(search_parameters)
        if built_model.extra_objective_vars and built_model.extra_objective_weights:
            built_model.routing.AddSearchMonitor(
                built_model.routing.solver().WeightedMinimize(
                    [built_model.routing.CostVar(), *built_model.extra_objective_vars],
                    [1, *built_model.extra_objective_weights],
                    1,
                )
            )

    @staticmethod
    def _problem_with_config(
        problem: PreprocessedProblem,
        config: schemas.OptimizationConfig,
    ) -> PreprocessedProblem:
        return replace(problem, config=config)

    @staticmethod
    def _full_service_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.minimize_truck_count = False
        config.minimize_distance = False
        config.minimize_time = False
        config.minimize_depot_operation_time = False
        config.soft_constraints = config.soft_constraints.model_copy(
            update={
                "time_window": False,
                "allow_unserved_orders": False,
                "allow_overtime": False,
                "priority_eta": False,
                "truck_category": False,
                "depot_operation_window": False,
                "max_route_duration": False,
                "max_vehicle_working_time": False,
                "max_total_distance_per_vehicle": False,
            }
        )
        return config

    @staticmethod
    def _optimization_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.soft_constraints = config.soft_constraints.model_copy(update={"allow_unserved_orders": False})
        config.allow_unserved_fallback = False
        return config

    @staticmethod
    def _partial_service_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.minimize_truck_count = False
        config.minimize_distance = False
        config.minimize_time = False
        config.minimize_depot_operation_time = False
        return config

    @staticmethod
    def _best_effort_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.soft_constraints = config.soft_constraints.model_copy(update={"allow_unserved_orders": True})
        config.allow_unserved_fallback = True
        config.penalties = config.penalties.model_copy(
            update={
                "unserved_order_penalty": max(
                    int(round(config.penalties.unserved_order_penalty)),
                    1_000_000_000,
                )
            }
        )
        return config

    @staticmethod
    def _cleanup_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.minimize_truck_count = False
        config.minimize_distance = False
        config.minimize_time = False
        config.minimize_depot_operation_time = False
        config.soft_constraints = config.soft_constraints.model_copy(update={"allow_unserved_orders": False})
        config.allow_unserved_fallback = False
        return config

    @staticmethod
    def _depot_refinement_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.minimize_truck_count = False
        config.minimize_depot_operation_time = True
        config.soft_constraints = config.soft_constraints.model_copy(update={"allow_unserved_orders": False})
        config.allow_unserved_fallback = False
        return config

    @staticmethod
    def _truck_count_refinement_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.minimize_truck_count = False
        config.minimize_depot_operation_time = True
        config.soft_constraints = config.soft_constraints.model_copy(update={"allow_unserved_orders": False})
        config.allow_unserved_fallback = False
        return config

    @staticmethod
    def _eligible_vehicle_indices(problem: PreprocessedProblem) -> list[int]:
        shipment_counts = [0] * len(problem.trucks)
        for shipment in problem.shipments:
            for vehicle_index in shipment.allowed_vehicle_indices:
                if 0 <= vehicle_index < len(shipment_counts):
                    shipment_counts[vehicle_index] += 1
        return [index for index, count in enumerate(shipment_counts) if count > 0]

    @staticmethod
    def _depot_mode_forced_vehicle_indices(problem: PreprocessedProblem) -> list[int]:
        eligible = OrToolsSolver._eligible_vehicle_indices(problem)
        if not eligible:
            return []
        target_count = min(len(eligible), len(problem.shipments))
        ranked = OrToolsSolver._ranked_eligible_vehicle_indices(problem, eligible)
        return sorted(ranked[:target_count])

    @staticmethod
    def _ranked_eligible_vehicle_indices(problem: PreprocessedProblem, eligible: list[int] | None = None) -> list[int]:
        if eligible is None:
            eligible = OrToolsSolver._eligible_vehicle_indices(problem)
        return sorted(
            eligible,
            key=lambda index: (
                -len([shipment for shipment in problem.shipments if index in shipment.allowed_vehicle_indices]),
                -problem.trucks[index].capacity_kl,
                index,
            ),
        )

    @staticmethod
    def _mode_activation_policy(problem: PreprocessedProblem) -> VehicleActivationPolicy | None:
        if problem.config.primary_objective == schemas.PrimaryObjective.MINIMIZE_DEPOT_OPERATION:
            forced = tuple(OrToolsSolver._depot_mode_forced_vehicle_indices(problem))
            if forced:
                return VehicleActivationPolicy(force_active_vehicle_indices=forced)
        return None

    @staticmethod
    def _visited_shipment_ids(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
    ) -> set[str]:
        routing = built_model.routing
        manager = built_model.manager
        if not all(
            hasattr(routing, attr)
            for attr in ("Start", "IsEnd", "NextVar")
        ) or not hasattr(manager, "IndexToNode"):
            return set()
        visited_shipments: set[str] = set()
        for vehicle_id in range(len(problem.trucks)):
            index = routing.Start(vehicle_id)
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                node_detail = problem.get_node(node)
                if node_detail is not None and node_detail.node_kind == "shipment":
                    visited_shipments.add(node_detail.order_id)
                index = assignment.Value(routing.NextVar(index))
        return visited_shipments

    @staticmethod
    def _count_unserved_shipments(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
    ) -> int:
        visited_shipments = OrToolsSolver._visited_shipment_ids(problem, built_model, assignment)
        return len([shipment for shipment in problem.shipments if shipment.order_id not in visited_shipments])

    @staticmethod
    def _active_vehicle_count(
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
        vehicle_count: int,
    ) -> int:
        routing = built_model.routing
        active_count = 0
        for vehicle_id in range(vehicle_count):
            if assignment.Value(routing.NextVar(routing.Start(vehicle_id))) != routing.End(vehicle_id):
                active_count += 1
        return active_count

    @staticmethod
    def _unserved_shipments(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
    ) -> list:
        visited_shipments = OrToolsSolver._visited_shipment_ids(problem, built_model, assignment)
        return [shipment for shipment in problem.shipments if shipment.order_id not in visited_shipments]

    @staticmethod
    def _shipment_vehicle_assignments(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
    ) -> dict[str, int]:
        routing = built_model.routing
        manager = built_model.manager
        if not all(
            hasattr(routing, attr)
            for attr in ("Start", "IsEnd", "NextVar")
        ) or not hasattr(manager, "IndexToNode"):
            return {}
        assignments: dict[str, int] = {}
        for vehicle_id in range(len(problem.trucks)):
            index = routing.Start(vehicle_id)
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                node_detail = problem.get_node(node)
                if node_detail is not None and node_detail.node_kind == "shipment":
                    assignments[node_detail.order_id] = vehicle_id
                index = assignment.Value(routing.NextVar(index))
        return assignments

    @staticmethod
    def _vehicle_route_metrics(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
    ) -> dict[int, VehicleRouteMetric]:
        routing = built_model.routing
        time_dimension = built_model.time_dimension
        if not all(hasattr(routing, attr) for attr in ("Start", "End")) or time_dimension is None:
            return {
                vehicle_index: VehicleRouteMetric(
                    vehicle_index=vehicle_index,
                    route_minutes=0,
                    end_minutes=0,
                    overtime_minutes=0,
                    shift_slack_minutes=hhmm_to_minutes(truck.shift_end),
                )
                for vehicle_index, truck in enumerate(problem.trucks)
            }

        metrics: dict[int, VehicleRouteMetric] = {}
        for vehicle_index, truck in enumerate(problem.trucks):
            start_index = routing.Start(vehicle_index)
            end_index = routing.End(vehicle_index)
            start_minutes = assignment.Value(time_dimension.CumulVar(start_index))
            end_minutes = assignment.Value(time_dimension.CumulVar(end_index))
            shift_end_minutes = hhmm_to_minutes(truck.shift_end)
            metrics[vehicle_index] = VehicleRouteMetric(
                vehicle_index=vehicle_index,
                route_minutes=max(0, end_minutes - start_minutes),
                end_minutes=end_minutes,
                overtime_minutes=max(0, end_minutes - shift_end_minutes),
                shift_slack_minutes=max(0, shift_end_minutes - end_minutes),
            )
        return metrics

    @staticmethod
    def _rank_cleanup_candidate_vehicles(
        shipment,
        route_metrics: dict[int, VehicleRouteMetric],
    ) -> list[int]:
        return sorted(
            shipment.allowed_vehicle_indices,
            key=lambda vehicle_index: (
                route_metrics[vehicle_index].route_minutes,
                route_metrics[vehicle_index].overtime_minutes,
                -route_metrics[vehicle_index].shift_slack_minutes,
                vehicle_index,
            ),
        )

    @staticmethod
    def _targeted_cleanup_candidate_limits(problem: PreprocessedProblem, unserved_count: int) -> list[int]:
        if unserved_count <= 0 or not problem.trucks:
            return []
        truck_count = len(problem.trucks)
        raw_limits = [1, 2, max(3, unserved_count), max(5, unserved_count * 2), truck_count]
        limits: list[int] = []
        for value in raw_limits:
            bounded = min(truck_count, max(1, value))
            if bounded not in limits:
                limits.append(bounded)
        return limits

    @staticmethod
    def _build_targeted_cleanup_problem(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
        *,
        max_candidates_per_shipment: int,
    ) -> PreprocessedProblem:
        unserved_shipments = OrToolsSolver._unserved_shipments(problem, built_model, assignment)
        if not unserved_shipments:
            return problem

        route_metrics = OrToolsSolver._vehicle_route_metrics(problem, built_model, assignment)
        candidate_by_shipment = {
            shipment.order_id: OrToolsSolver._rank_cleanup_candidate_vehicles(shipment, route_metrics)[
                :max_candidates_per_shipment
            ]
            for shipment in unserved_shipments
        }

        updated_nodes = []
        changed = False
        for node in problem.route_nodes:
            if node.node_kind != "shipment" or node.order_id not in candidate_by_shipment:
                updated_nodes.append(node)
                continue
            candidates = candidate_by_shipment[node.order_id] or node.allowed_vehicle_indices
            if candidates != node.allowed_vehicle_indices:
                changed = True
                updated_nodes.append(replace(node, allowed_vehicle_indices=candidates))
                continue
            updated_nodes.append(node)
        if not changed:
            return problem
        return replace(problem, route_nodes=updated_nodes)

    @staticmethod
    def _build_forced_residual_insertion_problem(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
        *,
        max_candidates_per_shipment: int,
    ) -> PreprocessedProblem:
        served_assignments = OrToolsSolver._shipment_vehicle_assignments(problem, built_model, assignment)
        unserved_shipments = OrToolsSolver._unserved_shipments(problem, built_model, assignment)
        if not unserved_shipments:
            return problem

        route_metrics = OrToolsSolver._vehicle_route_metrics(problem, built_model, assignment)
        candidate_by_shipment = {
            shipment.order_id: OrToolsSolver._rank_cleanup_candidate_vehicles(shipment, route_metrics)[
                :max_candidates_per_shipment
            ]
            for shipment in unserved_shipments
        }

        updated_nodes = []
        changed = False
        for node in problem.route_nodes:
            if node.node_kind != "shipment":
                updated_nodes.append(node)
                continue
            if node.order_id in candidate_by_shipment:
                candidates = candidate_by_shipment[node.order_id] or node.allowed_vehicle_indices
            elif node.order_id in served_assignments:
                candidates = [served_assignments[node.order_id]]
            else:
                candidates = node.allowed_vehicle_indices
            if candidates != node.allowed_vehicle_indices:
                changed = True
                updated_nodes.append(replace(node, allowed_vehicle_indices=candidates))
                continue
            updated_nodes.append(node)
        if not changed:
            return problem
        return replace(problem, route_nodes=updated_nodes)

    @staticmethod
    def _extract_vehicle_routes(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
    ) -> list[list[int]]:
        routing = built_model.routing
        manager = built_model.manager
        routes: list[list[int]] = []
        for vehicle_id in range(len(problem.trucks)):
            vehicle_route: list[int] = []
            index = routing.Start(vehicle_id)
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                if node > 0:
                    vehicle_route.append(node)
                index = assignment.Value(routing.NextVar(index))
            routes.append(vehicle_route)
        return routes

    @staticmethod
    def _build_manual_residual_routes(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
        *,
        max_candidates_per_shipment: int,
    ) -> list[list[int]] | None:
        routes = OrToolsSolver._extract_vehicle_routes(problem, built_model, assignment)
        used_nodes = {node for route in routes for node in route}
        route_metrics = OrToolsSolver._vehicle_route_metrics(problem, built_model, assignment)
        unserved_shipments = OrToolsSolver._unserved_shipments(problem, built_model, assignment)
        if not unserved_shipments:
            return routes

        reload_nodes = [node for node in problem.reload_nodes if node.node_index not in used_nodes]
        append_counts = [0] * len(problem.trucks)

        for shipment in sorted(
            unserved_shipments,
            key=lambda item: (len(item.allowed_vehicle_indices), -item.demand_kl, item.node_index),
        ):
            candidates = OrToolsSolver._rank_cleanup_candidate_vehicles(shipment, route_metrics)[:max_candidates_per_shipment]
            assigned = False
            for vehicle_index in sorted(
                candidates,
                key=lambda idx: (
                    append_counts[idx],
                    route_metrics[idx].route_minutes,
                    route_metrics[idx].overtime_minutes,
                    -route_metrics[idx].shift_slack_minutes,
                    idx,
                ),
            ):
                reload_node = next(
                    (
                        node
                        for node in reload_nodes
                        if vehicle_index in node.allowed_vehicle_indices and node.node_index not in used_nodes
                    ),
                    None,
                )
                if reload_node is None:
                    continue
                routes[vehicle_index].extend([reload_node.node_index, shipment.node_index])
                used_nodes.add(reload_node.node_index)
                used_nodes.add(shipment.node_index)
                append_counts[vehicle_index] += 1
                assigned = True
                break
            if not assigned:
                return None
        return routes

    @staticmethod
    def _build_balanced_full_service_routes(
        problem: PreprocessedProblem,
        active_vehicle_indices: list[int],
    ) -> list[list[int]] | None:
        routes = [[] for _ in problem.trucks]
        active_set = set(active_vehicle_indices)
        if not active_set:
            return None

        reload_nodes_by_vehicle: dict[int, list] = {}
        for node in sorted(
            problem.reload_nodes,
            key=lambda item: (
                item.reload_vehicle_index if item.reload_vehicle_index is not None else len(problem.trucks),
                item.reload_trip_number if item.reload_trip_number is not None else 0,
                item.node_index,
            ),
        ):
            vehicle_index = node.reload_vehicle_index
            if vehicle_index is None:
                continue
            reload_nodes_by_vehicle.setdefault(vehicle_index, []).append(node)

        trip_counts = {vehicle_index: 0 for vehicle_index in active_vehicle_indices}
        for shipment in sorted(
            problem.shipments,
            key=lambda item: (len(item.allowed_vehicle_indices), -item.demand_kl, item.node_index),
        ):
            candidates = [
                vehicle_index
                for vehicle_index in active_vehicle_indices
                if vehicle_index in shipment.allowed_vehicle_indices
            ]
            if not candidates:
                return None
            chosen_vehicle = min(
                candidates,
                key=lambda vehicle_index: (
                    trip_counts[vehicle_index],
                    len(routes[vehicle_index]),
                    vehicle_index,
                ),
            )
            if trip_counts[chosen_vehicle] > 0:
                reload_pool = reload_nodes_by_vehicle.get(chosen_vehicle, [])
                if not reload_pool:
                    return None
                routes[chosen_vehicle].append(reload_pool.pop(0).node_index)
            routes[chosen_vehicle].append(shipment.node_index)
            trip_counts[chosen_vehicle] += 1

        if any(trip_counts[vehicle_index] == 0 for vehicle_index in active_vehicle_indices):
            return None
        return routes

    @staticmethod
    def _solve_from_manual_routes(
        problem: PreprocessedProblem,
        routes: list[list[int]],
        *,
        time_limit_seconds: int,
        include_soft_priority_eta_objective: bool,
        local_search_metaheuristic: str | None = None,
        activation_policy: VehicleActivationPolicy | None = None,
    ) -> StageSolveResult:
        built_model = build_routing_model_with_options(
            problem,
            include_soft_priority_eta_objective=include_soft_priority_eta_objective,
            activation_policy=activation_policy,
        )
        search_parameters = OrToolsSolver._build_search_parameters(
            problem,
            time_limit_seconds=time_limit_seconds,
            local_search_metaheuristic=local_search_metaheuristic,
        )
        OrToolsSolver._close_model(built_model, search_parameters)
        seed_assignment = built_model.routing.ReadAssignmentFromRoutes(routes, True)
        if seed_assignment is None:
            return StageSolveResult(
                built_model=built_model,
                assignment=None,
                search_status=built_model.routing.status(),
            )
        assignment = built_model.routing.SolveFromAssignmentWithParameters(seed_assignment, search_parameters)
        return StageSolveResult(
            built_model=built_model,
            assignment=assignment or seed_assignment,
            search_status=built_model.routing.status(),
        )

    @staticmethod
    def _allocate_best_effort_budgets(total_seconds: int) -> tuple[int, int, int, int, int]:
        weights = [35, 20, 15, 15, 15]
        budget_total = max(len(weights), int(total_seconds))
        allocated = [0, 0, 0, 0, 0]
        remaining = budget_total
        total_weight = sum(weights)
        for index, weight in enumerate(weights):
            slots_left = len(weights) - index
            share = max(1, int((budget_total * weight) / total_weight))
            share = min(share, remaining - (slots_left - 1))
            allocated[index] = share
            remaining -= share
        while remaining > 0:
            for index in range(len(allocated)):
                if remaining <= 0:
                    break
                allocated[index] += 1
                remaining -= 1
        return tuple(allocated)

    @staticmethod
    def _allocate_cleanup_attempt_budgets(total_seconds: int, attempts: int) -> list[int]:
        if total_seconds <= 0 or attempts <= 0:
            return []
        per_attempt = max(1, total_seconds // attempts)
        remainder = max(0, total_seconds - (per_attempt * attempts))
        return [per_attempt + (1 if index < remainder else 0) for index in range(attempts)]

    @staticmethod
    def _allocate_stage_budgets(
        total_seconds: int,
        *,
        include_repair: bool,
    ) -> tuple[int, int, int, int]:
        weights = [40, 25 if include_repair else 0, 20, 15]
        positive_weights = [weight for weight in weights if weight > 0]
        if not positive_weights:
            return (max(1, total_seconds), 0, 0, 0)
        budget_total = max(len(positive_weights), int(total_seconds))
        allocated = [0, 0, 0, 0]
        remaining = budget_total
        remaining_weight = sum(positive_weights)
        for index, weight in enumerate(weights):
            if weight <= 0:
                continue
            slots_left = sum(1 for item in weights[index:] if item > 0)
            share = max(1, int((budget_total * weight) / max(1, sum(weights))))
            share = min(share, remaining - (slots_left - 1))
            allocated[index] = share
            remaining -= share
            remaining_weight -= weight
        positive_indices = [index for index, weight in enumerate(weights) if weight > 0]
        while remaining > 0 and positive_indices:
            for index in positive_indices:
                if remaining <= 0:
                    break
                allocated[index] += 1
                remaining -= 1
        return allocated[0], allocated[1], allocated[2], allocated[3]

    @staticmethod
    def _allocate_full_service_budgets(total_seconds: int) -> tuple[int, int]:
        strict_seconds = max(1, int(round(total_seconds * 0.6)))
        optimize_seconds = max(1, total_seconds - strict_seconds)
        return strict_seconds, optimize_seconds

    @staticmethod
    def _repair_metaheuristic(problem: PreprocessedProblem) -> str:
        current = problem.config.solver_options.local_search_metaheuristic
        if current == "TABU_SEARCH":
            return "SIMULATED_ANNEALING"
        return "TABU_SEARCH"

    def _solve_stage(
        self,
        problem: PreprocessedProblem,
        *,
        time_limit_seconds: int,
        include_soft_priority_eta_objective: bool,
        local_search_metaheuristic: str | None = None,
        activation_policy: VehicleActivationPolicy | None = None,
    ) -> StageSolveResult:
        built_model = build_routing_model_with_options(
            problem,
            include_soft_priority_eta_objective=include_soft_priority_eta_objective,
            activation_policy=activation_policy,
        )
        search_parameters = self._build_search_parameters(
            problem,
            time_limit_seconds=time_limit_seconds,
            local_search_metaheuristic=local_search_metaheuristic,
        )
        self._close_model(built_model, search_parameters)
        assignment = built_model.routing.SolveWithParameters(search_parameters)
        return StageSolveResult(
            built_model=built_model,
            assignment=assignment,
            search_status=built_model.routing.status(),
        )

    def _refine_stage(
        self,
        problem: PreprocessedProblem,
        *,
        seed_model: BuiltModel,
        seed_assignment: pywrapcp.Assignment,
        time_limit_seconds: int,
        include_soft_priority_eta_objective: bool,
        local_search_metaheuristic: str | None = None,
        activation_policy: VehicleActivationPolicy | None = None,
    ) -> StageSolveResult:
        built_model = build_routing_model_with_options(
            problem,
            include_soft_priority_eta_objective=include_soft_priority_eta_objective,
            activation_policy=activation_policy,
        )
        search_parameters = self._build_search_parameters(
            problem,
            time_limit_seconds=time_limit_seconds,
            local_search_metaheuristic=local_search_metaheuristic,
        )
        self._close_model(built_model, search_parameters)
        seed = built_model.routing.solver().Assignment()
        built_model.routing.SetAssignmentFromOtherModelAssignment(
            seed,
            seed_model.routing,
            seed_assignment,
        )
        assignment = built_model.routing.SolveFromAssignmentWithParameters(seed, search_parameters)
        return StageSolveResult(
            built_model=built_model,
            assignment=assignment,
            search_status=built_model.routing.status(),
        )

    def _run_targeted_cleanup_repair(
        self,
        problem: PreprocessedProblem,
        *,
        seed_model: BuiltModel,
        seed_assignment: pywrapcp.Assignment,
        current_unserved: int,
        time_limit_seconds: int,
        activation_policy: VehicleActivationPolicy | None = None,
    ) -> tuple[BuiltModel, pywrapcp.Assignment, int] | None:
        if time_limit_seconds <= 0 or current_unserved <= 0:
            return None

        cleanup_problem = self._problem_with_config(problem, self._cleanup_config(problem))
        candidate_limits = self._targeted_cleanup_candidate_limits(cleanup_problem, current_unserved)
        if not candidate_limits:
            return None

        attempt_budgets = self._allocate_cleanup_attempt_budgets(time_limit_seconds, len(candidate_limits))
        best_model = seed_model
        best_assignment = seed_assignment
        best_unserved = current_unserved
        improved = False

        for candidate_limit, attempt_seconds in zip(candidate_limits, attempt_budgets, strict=False):
            targeted_problem = self._build_targeted_cleanup_problem(
                cleanup_problem,
                best_model,
                best_assignment,
                max_candidates_per_shipment=candidate_limit,
            )
            attempt = self._refine_stage(
                targeted_problem,
                seed_model=best_model,
                seed_assignment=best_assignment,
                time_limit_seconds=attempt_seconds,
                include_soft_priority_eta_objective=False,
                local_search_metaheuristic=self._repair_metaheuristic(problem),
                activation_policy=activation_policy,
            )
            if attempt.assignment is None:
                continue
            attempt_unserved = self._count_unserved_shipments(
                targeted_problem,
                attempt.built_model,
                attempt.assignment,
            )
            if attempt_unserved < best_unserved:
                best_model = attempt.built_model
                best_assignment = attempt.assignment
                best_unserved = attempt_unserved
                improved = True
                if best_unserved == 0:
                    break

        if not improved:
            return None
        return best_model, best_assignment, best_unserved

    def _run_forced_residual_insertion(
        self,
        problem: PreprocessedProblem,
        *,
        seed_model: BuiltModel,
        seed_assignment: pywrapcp.Assignment,
        current_unserved: int,
        time_limit_seconds: int,
        activation_policy: VehicleActivationPolicy | None = None,
    ) -> tuple[BuiltModel, pywrapcp.Assignment, int] | None:
        if time_limit_seconds <= 0 or current_unserved <= 0:
            return None

        cleanup_problem = self._problem_with_config(problem, self._cleanup_config(problem))
        candidate_limits = self._targeted_cleanup_candidate_limits(cleanup_problem, current_unserved)
        if not candidate_limits:
            return None

        metaheuristics = [
            self._repair_metaheuristic(problem),
            "SIMULATED_ANNEALING",
        ]
        attempts = [(candidate_limit, metaheuristic) for candidate_limit in candidate_limits for metaheuristic in metaheuristics]
        attempt_budgets = self._allocate_cleanup_attempt_budgets(time_limit_seconds, len(attempts))
        best_model = seed_model
        best_assignment = seed_assignment
        best_unserved = current_unserved
        improved = False

        for (candidate_limit, metaheuristic), attempt_seconds in zip(attempts, attempt_budgets, strict=False):
            forced_problem = self._build_forced_residual_insertion_problem(
                cleanup_problem,
                best_model,
                best_assignment,
                max_candidates_per_shipment=candidate_limit,
            )
            attempt = self._refine_stage(
                forced_problem,
                seed_model=best_model,
                seed_assignment=best_assignment,
                time_limit_seconds=attempt_seconds,
                include_soft_priority_eta_objective=False,
                local_search_metaheuristic=metaheuristic,
                activation_policy=activation_policy,
            )
            if attempt.assignment is None:
                continue
            attempt_unserved = self._count_unserved_shipments(
                forced_problem,
                attempt.built_model,
                attempt.assignment,
            )
            if attempt_unserved < best_unserved:
                best_model = attempt.built_model
                best_assignment = attempt.assignment
                best_unserved = attempt_unserved
                improved = True
                if best_unserved == 0:
                    break

        if best_unserved > 0 and time_limit_seconds > 0:
            manual_routes = self._build_manual_residual_routes(
                cleanup_problem,
                best_model,
                best_assignment,
                max_candidates_per_shipment=max(1, min(len(problem.trucks), max(3, current_unserved))),
            )
            if manual_routes is not None:
                manual_attempt = self._solve_from_manual_routes(
                    cleanup_problem,
                    manual_routes,
                    time_limit_seconds=max(1, time_limit_seconds),
                    include_soft_priority_eta_objective=False,
                    local_search_metaheuristic="SIMULATED_ANNEALING",
                    activation_policy=activation_policy,
                )
                if manual_attempt.assignment is not None:
                    manual_unserved = self._count_unserved_shipments(
                        cleanup_problem,
                        manual_attempt.built_model,
                        manual_attempt.assignment,
                    )
                    if manual_unserved < best_unserved:
                        best_model = manual_attempt.built_model
                        best_assignment = manual_attempt.assignment
                        best_unserved = manual_unserved
                        improved = True

        if not improved:
            return None
        return best_model, best_assignment, best_unserved

    def _run_best_effort_pipeline(
        self,
        problem: PreprocessedProblem,
        *,
        started: float,
        total_seconds: int,
        best_effort_prefix: str | None = None,
    ) -> SolverOutput:
        activation_policy = self._mode_activation_policy(problem)
        service_problem = self._problem_with_config(problem, self._partial_service_config(problem))
        quality_problem = self._problem_with_config(problem, self._optimization_config(problem))
        service_seconds, repair_seconds, cleanup_seconds, quality_seconds, full_seconds = self._allocate_best_effort_budgets(
            total_seconds
        )

        service_result = self._solve_stage(
            service_problem,
            time_limit_seconds=service_seconds,
            include_soft_priority_eta_objective=False,
            activation_policy=activation_policy,
        )
        if service_result.assignment is None:
            runtime = time.perf_counter() - started
            return SolverOutput(
                built_model=service_result.built_model,
                assignment=None,
                runtime_seconds=runtime,
                message=self._build_message(service_result.search_status, None),
                search_status=service_result.search_status,
            )

        best_model = service_result.built_model
        best_assignment = service_result.assignment
        best_unserved = self._count_unserved_shipments(service_problem, best_model, best_assignment)
        repaired = False
        cleanup_refined = False
        forced_cleanup_refined = False
        quality_refined = False
        cost_refined = False

        if repair_seconds > 0 and best_unserved > 0:
            repair_result = self._refine_stage(
                service_problem,
                seed_model=best_model,
                seed_assignment=best_assignment,
                time_limit_seconds=repair_seconds,
                include_soft_priority_eta_objective=False,
                local_search_metaheuristic=self._repair_metaheuristic(problem),
                activation_policy=activation_policy,
            )
            if repair_result.assignment is not None:
                repair_unserved = self._count_unserved_shipments(
                    service_problem,
                    repair_result.built_model,
                    repair_result.assignment,
                )
                if repair_unserved <= best_unserved:
                    repaired = repair_unserved < best_unserved
                    best_model = repair_result.built_model
                    best_assignment = repair_result.assignment
                    best_unserved = repair_unserved

        if cleanup_seconds > 0 and best_unserved > 0:
            targeted_cleanup_seconds = max(1, cleanup_seconds // 2)
            forced_cleanup_seconds = max(0, cleanup_seconds - targeted_cleanup_seconds)
            cleanup_result = self._run_targeted_cleanup_repair(
                problem,
                seed_model=best_model,
                seed_assignment=best_assignment,
                current_unserved=best_unserved,
                time_limit_seconds=targeted_cleanup_seconds,
                activation_policy=activation_policy,
            )
            if cleanup_result is not None:
                best_model, best_assignment, best_unserved = cleanup_result
                cleanup_refined = True

        if cleanup_seconds > 0 and best_unserved > 0:
            targeted_cleanup_seconds = max(1, cleanup_seconds // 2)
            forced_cleanup_seconds = max(0, cleanup_seconds - targeted_cleanup_seconds)
            forced_cleanup_result = self._run_forced_residual_insertion(
                problem,
                seed_model=best_model,
                seed_assignment=best_assignment,
                current_unserved=best_unserved,
                time_limit_seconds=forced_cleanup_seconds,
                activation_policy=activation_policy,
            )
            if forced_cleanup_result is not None:
                best_model, best_assignment, best_unserved = forced_cleanup_result
                forced_cleanup_refined = True

        if quality_seconds > 0:
            optimize_result = self._refine_stage(
                quality_problem,
                seed_model=best_model,
                seed_assignment=best_assignment,
                time_limit_seconds=quality_seconds,
                include_soft_priority_eta_objective=quality_problem.config.soft_constraints.priority_eta,
                activation_policy=activation_policy,
            )
            if optimize_result.assignment is not None:
                optimize_unserved = self._count_unserved_shipments(
                    quality_problem,
                    optimize_result.built_model,
                    optimize_result.assignment,
                )
                if optimize_unserved <= best_unserved:
                    best_model = optimize_result.built_model
                    best_assignment = optimize_result.assignment
                    best_unserved = optimize_unserved
                    quality_refined = True

        if full_seconds > 0:
            cost_result = self._refine_stage(
                problem,
                seed_model=best_model,
                seed_assignment=best_assignment,
                time_limit_seconds=full_seconds,
                include_soft_priority_eta_objective=problem.config.soft_constraints.priority_eta,
                activation_policy=activation_policy,
            )
            if cost_result.assignment is not None:
                cost_unserved = self._count_unserved_shipments(
                    problem,
                    cost_result.built_model,
                    cost_result.assignment,
                )
                if cost_unserved <= best_unserved:
                    best_model = cost_result.built_model
                    best_assignment = cost_result.assignment
                    best_unserved = cost_unserved
                    cost_refined = True

        runtime = time.perf_counter() - started
        message_prefix = f"{best_effort_prefix} " if best_effort_prefix else ""
        if best_unserved == 0:
            if forced_cleanup_refined:
                message = (
                    f"{message_prefix}Optimization finished after forced residual insertion and optimization."
                ).strip()
            elif cleanup_refined:
                message = (
                    f"{message_prefix}Optimization finished after targeted cleanup repair and optimization."
                ).strip()
            else:
                message = f"{message_prefix}Optimization finished after best-effort repair and optimization.".strip()
        elif repaired or cleanup_refined or forced_cleanup_refined or quality_refined or cost_refined:
            if forced_cleanup_refined:
                refinement_steps = "repair, targeted cleanup, forced residual insertion, and optimization"
            elif cleanup_refined:
                refinement_steps = "repair, targeted cleanup, and optimization"
            else:
                refinement_steps = "repair and optimization"
            message = (
                f"{message_prefix}Optimization finished with best-effort partial routes after {refinement_steps}."
            ).strip()
        else:
            message = f"{message_prefix}Optimization finished with the best partial solution found.".strip()
        return SolverOutput(
            built_model=best_model,
            assignment=best_assignment,
            runtime_seconds=runtime,
            message=message,
            search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
        )

    def _run_full_service_depot_pipeline(
        self,
        problem: PreprocessedProblem,
        *,
        started: float,
        total_seconds: int,
    ) -> SolverOutput:
        strict_problem = self._problem_with_config(problem, self._full_service_config(problem))
        optimize_problem = self._problem_with_config(problem, self._depot_refinement_config(problem))
        strict_seconds, optimize_seconds = self._allocate_full_service_budgets(total_seconds)
        activation_policy = self._mode_activation_policy(problem)

        strict_result = self._solve_stage(
            strict_problem,
            time_limit_seconds=strict_seconds,
            include_soft_priority_eta_objective=False,
            activation_policy=activation_policy,
        )
        if strict_result.assignment is None and activation_policy is not None:
            manual_routes = self._build_balanced_full_service_routes(
                strict_problem,
                list(activation_policy.force_active_vehicle_indices),
            )
            if manual_routes is not None:
                strict_result = self._solve_from_manual_routes(
                    strict_problem,
                    manual_routes,
                    time_limit_seconds=strict_seconds,
                    include_soft_priority_eta_objective=False,
                    activation_policy=activation_policy,
                )
        if strict_result.assignment is None:
            runtime = time.perf_counter() - started
            return SolverOutput(
                built_model=strict_result.built_model,
                assignment=None,
                runtime_seconds=runtime,
                message=self._build_message(strict_result.search_status, None),
                search_status=strict_result.search_status,
            )

        if optimize_seconds <= 0:
            runtime = time.perf_counter() - started
            return SolverOutput(
                built_model=strict_result.built_model,
                assignment=strict_result.assignment,
                runtime_seconds=runtime,
                message="Optimization finished after strict full-service solve.",
                search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
            )

        optimize_result = self._refine_stage(
            optimize_problem,
            seed_model=strict_result.built_model,
            seed_assignment=strict_result.assignment,
            time_limit_seconds=optimize_seconds,
            include_soft_priority_eta_objective=optimize_problem.config.soft_constraints.priority_eta,
            activation_policy=activation_policy,
        )
        runtime = time.perf_counter() - started
        if optimize_result.assignment is not None:
            return SolverOutput(
                built_model=optimize_result.built_model,
                assignment=optimize_result.assignment,
                runtime_seconds=runtime,
                message="Optimization finished after strict full-service solve and seeded cost refinement.",
                search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
            )
        return SolverOutput(
            built_model=strict_result.built_model,
            assignment=strict_result.assignment,
            runtime_seconds=runtime,
            message="Optimization finished after strict full-service solve; cost refinement kept the seeded full-service plan.",
            search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
        )

    def _run_full_service_min_truck_pipeline(
        self,
        problem: PreprocessedProblem,
        *,
        started: float,
        total_seconds: int,
    ) -> SolverOutput:
        strict_problem = self._problem_with_config(problem, self._full_service_config(problem))
        strict_seconds = max(1, int(round(total_seconds * 0.3)))
        search_seconds = max(1, total_seconds - strict_seconds)
        ranked_eligible = self._ranked_eligible_vehicle_indices(problem)

        strict_result = self._solve_stage(
            strict_problem,
            time_limit_seconds=strict_seconds,
            include_soft_priority_eta_objective=False,
        )
        if strict_result.assignment is None and ranked_eligible:
            best_seed_result: StageSolveResult | None = None
            seed_attempt_seconds = max(1, search_seconds // max(1, len(ranked_eligible)))
            for candidate_active_count in range(1, len(ranked_eligible) + 1):
                candidate_vehicle_indices = ranked_eligible[:candidate_active_count]
                manual_routes = self._build_balanced_full_service_routes(strict_problem, candidate_vehicle_indices)
                if manual_routes is None:
                    continue
                candidate_policy = VehicleActivationPolicy(max_active_vehicles=candidate_active_count)
                seed_result = self._solve_from_manual_routes(
                    strict_problem,
                    manual_routes,
                    time_limit_seconds=seed_attempt_seconds,
                    include_soft_priority_eta_objective=False,
                    activation_policy=candidate_policy,
                )
                if seed_result.assignment is not None:
                    best_seed_result = seed_result
                    break
            if best_seed_result is not None:
                strict_result = best_seed_result
        if strict_result.assignment is None:
            runtime = time.perf_counter() - started
            return SolverOutput(
                built_model=strict_result.built_model,
                assignment=None,
                runtime_seconds=runtime,
                message=self._build_message(strict_result.search_status, None),
                search_status=strict_result.search_status,
            )

        best_model = strict_result.built_model
        best_assignment = strict_result.assignment
        best_active_count = self._active_vehicle_count(best_model, best_assignment, len(problem.trucks))

        if best_active_count > 1 and search_seconds > 0:
            per_attempt_seconds = max(1, search_seconds // best_active_count)
            for candidate_active_count in range(best_active_count - 1, 0, -1):
                candidate_policy = VehicleActivationPolicy(max_active_vehicles=candidate_active_count)
                attempt = self._solve_stage(
                    strict_problem,
                    time_limit_seconds=per_attempt_seconds,
                    include_soft_priority_eta_objective=False,
                    activation_policy=candidate_policy,
                )
                if attempt.assignment is None:
                    break
                best_model = attempt.built_model
                best_assignment = attempt.assignment
                best_active_count = candidate_active_count

        refine_problem = self._problem_with_config(problem, self._truck_count_refinement_config(problem))
        refine_policy = VehicleActivationPolicy(max_active_vehicles=best_active_count)
        refine_result = self._refine_stage(
            refine_problem,
            seed_model=best_model,
            seed_assignment=best_assignment,
            time_limit_seconds=max(1, total_seconds // 4),
            include_soft_priority_eta_objective=refine_problem.config.soft_constraints.priority_eta,
            activation_policy=refine_policy,
        )
        runtime = time.perf_counter() - started
        if refine_result.assignment is not None:
            return SolverOutput(
                built_model=refine_result.built_model,
                assignment=refine_result.assignment,
                runtime_seconds=runtime,
                message="Optimization finished after full-service solve, active-truck reduction, and seeded refinement.",
                search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
            )
        return SolverOutput(
            built_model=best_model,
            assignment=best_assignment,
            runtime_seconds=runtime,
            message="Optimization finished after full-service solve and active-truck reduction.",
            search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
        )

    def _run_full_service_pipeline(
        self,
        problem: PreprocessedProblem,
        *,
        started: float,
        total_seconds: int,
    ) -> SolverOutput:
        if problem.config.primary_objective == schemas.PrimaryObjective.MINIMIZE_DEPOT_OPERATION:
            return self._run_full_service_depot_pipeline(
                problem,
                started=started,
                total_seconds=total_seconds,
            )
        return self._run_full_service_min_truck_pipeline(
            problem,
            started=started,
            total_seconds=total_seconds,
        )

    def solve(self, problem: PreprocessedProblem) -> SolverOutput:
        started = time.perf_counter()
        logger.info("Running OR-Tools with %s shipments and %s vehicles", len(problem.shipments), len(problem.trucks))
        effective_total_seconds = self._effective_time_limit_seconds(
            problem,
            problem.config.solver_options.max_solver_seconds,
        )
        strict_output = self._run_full_service_pipeline(
            problem,
            started=started,
            total_seconds=effective_total_seconds,
        )
        if strict_output.assignment is not None:
            return strict_output

        if not problem.config.allow_unserved_fallback:
            return strict_output

        logger.info(
            "Strict full-service solve failed for scenario %s; retrying with best-effort partial fallback.",
            problem.dispatch_date,
        )
        best_effort_problem = self._problem_with_config(problem, self._best_effort_config(problem))
        best_effort_output = self._run_best_effort_pipeline(
            best_effort_problem,
            started=started,
            total_seconds=effective_total_seconds,
            best_effort_prefix="Strict full-service solve failed; returning best-effort partial solution.",
        )
        if best_effort_output.assignment is not None:
            return best_effort_output

        return strict_output
