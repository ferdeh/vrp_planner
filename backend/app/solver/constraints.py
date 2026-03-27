"""Constraint helpers for OR-Tools routing model."""

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.constraint_solver import pywrapcp

from app.services.preprocessing_service import PreprocessedProblem
from app.utils.time_utils import hhmm_to_minutes


@dataclass
class TimeConstraintArtifacts:
    dimension: pywrapcp.RoutingDimension
    extra_objective_vars: list[pywrapcp.IntVar] = field(default_factory=list)
    extra_objective_weights: list[int] = field(default_factory=list)


def apply_capacity_constraints(
    routing: pywrapcp.RoutingModel,
    manager: pywrapcp.RoutingIndexManager,
    problem: PreprocessedProblem,
) -> pywrapcp.RoutingDimension:
    """Create load and per-trip compartment usage dimensions."""

    max_capacity = max(int(round(truck.capacity_kl * 1000)) for truck in problem.trucks)
    max_compartment_count = max(max(1, len(truck.compartments)) for truck in problem.trucks)

    def demand_callback(from_index: int) -> int:
        node = manager.IndexToNode(from_index)
        detail = problem.get_node(node)
        if detail is None:
            return 0
        if detail.node_kind == "reload":
            return -max_capacity
        return int(round(detail.demand_kl * 1000))

    demand_index = routing.RegisterUnaryTransitCallback(demand_callback)
    capacities = [int(round(truck.capacity_kl * 1000)) for truck in problem.trucks]
    routing.AddDimensionWithVehicleCapacity(
        demand_index,
        max_capacity,
        capacities,
        True,
        "Capacity",
    )
    dimension = routing.GetDimensionOrDie("Capacity")
    for node in problem.shipments:
        dimension.SlackVar(manager.NodeToIndex(node.node_index)).SetValue(0)

    def compartment_usage_callback(from_index: int) -> int:
        node = manager.IndexToNode(from_index)
        detail = problem.get_node(node)
        if detail is None:
            return 0
        if detail.node_kind == "reload":
            return -max_compartment_count
        return 1

    compartment_usage_index = routing.RegisterUnaryTransitCallback(compartment_usage_callback)
    routing.AddDimensionWithVehicleCapacity(
        compartment_usage_index,
        max_compartment_count,
        [max(1, len(truck.compartments)) for truck in problem.trucks],
        True,
        "Compartments",
    )
    compartment_dimension = routing.GetDimensionOrDie("Compartments")
    for node in problem.shipments:
        compartment_dimension.SlackVar(manager.NodeToIndex(node.node_index)).SetValue(0)
    return dimension


def apply_distance_constraints(
    routing: pywrapcp.RoutingModel,
    manager: pywrapcp.RoutingIndexManager,
    problem: PreprocessedProblem,
) -> pywrapcp.RoutingDimension:
    """Create the distance dimension."""

    def distance_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        from_detail = problem.get_node(from_node)
        to_detail = problem.get_node(to_node)
        from_name = "DEPOT" if from_detail is None else from_detail.matrix_node_name
        to_name = "DEPOT" if to_detail is None else to_detail.matrix_node_name
        return int(problem.distance_matrix[problem.matrix_positions[from_name]][problem.matrix_positions[to_name]])

    callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.AddDimension(
        callback_index,
        0,
        10**9,
        True,
        "Distance",
    )
    dimension = routing.GetDimensionOrDie("Distance")
    if problem.config.hard_constraints.max_total_distance_per_vehicle and problem.config.max_total_distance_per_vehicle_km:
        for vehicle_id in range(len(problem.trucks)):
            dimension.CumulVar(routing.End(vehicle_id)).SetMax(problem.config.max_total_distance_per_vehicle_km)
    elif (
        problem.config.soft_constraints.max_total_distance_per_vehicle
        and problem.config.max_total_distance_per_vehicle_km
    ):
        penalty = max(1, int(problem.config.penalties.distance_weight))
        for vehicle_id in range(len(problem.trucks)):
            dimension.SetCumulVarSoftUpperBound(
                routing.End(vehicle_id),
                problem.config.max_total_distance_per_vehicle_km,
                penalty,
            )
    return dimension


def apply_time_constraints(
    routing: pywrapcp.RoutingModel,
    manager: pywrapcp.RoutingIndexManager,
    problem: PreprocessedProblem,
) -> TimeConstraintArtifacts:
    """Create the time dimension and apply windows/shift policies."""

    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        from_detail = problem.get_node(from_node)
        to_detail = problem.get_node(to_node)
        from_name = "DEPOT" if from_detail is None else from_detail.matrix_node_name
        to_name = "DEPOT" if to_detail is None else to_detail.matrix_node_name
        service = 0 if from_detail is None else from_detail.service_time_minutes
        travel = problem.time_matrix[problem.matrix_positions[from_name]][problem.matrix_positions[to_name]]
        return int(service + travel)

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    horizon = 24 * 60 * 2
    routing.AddDimension(
        time_callback_index,
        horizon,
        horizon,
        False,
        "Time",
    )
    dimension = routing.GetDimensionOrDie("Time")
    solver = routing.solver()
    depot_service_intervals: list[pywrapcp.IntervalVar] = []
    depot_service_demands: list[int] = []
    depot_operation_active_vars: list[pywrapcp.IntVar] = []
    depot_operation_start_vars: list[pywrapcp.IntVar] = []
    depot_operation_end_vars: list[pywrapcp.IntVar] = []
    extra_objective_vars: list[pywrapcp.IntVar] = []
    extra_objective_weights: list[int] = []

    def register_depot_operation_window(
        condition: pywrapcp.IntVar,
        start_var: pywrapcp.IntVar,
        end_var: pywrapcp.IntVar,
        name_prefix: str,
    ) -> None:
        active_start = solver.IntVar(0, horizon, f"{name_prefix}_active_start")
        active_end = solver.IntVar(0, horizon, f"{name_prefix}_active_end")
        solver.Add(active_start == solver.ConditionalExpression(condition, start_var, horizon))
        solver.Add(active_end == solver.ConditionalExpression(condition, end_var, 0))
        depot_operation_active_vars.append(condition)
        depot_operation_start_vars.append(active_start)
        depot_operation_end_vars.append(active_end)

    for vehicle_id, truck in enumerate(problem.trucks):
        start_var = dimension.CumulVar(routing.Start(vehicle_id))
        end_var = dimension.CumulVar(routing.End(vehicle_id))
        shift_start = hhmm_to_minutes(truck.shift_start)
        shift_end = hhmm_to_minutes(truck.shift_end)
        working_time_limit = (
            shift_end
            if not problem.config.max_vehicle_working_time_minutes
            else min(shift_end, shift_start + problem.config.max_vehicle_working_time_minutes)
        )
        start_var.SetRange(shift_start, shift_end)
        routing.AddVariableMinimizedByFinalizer(start_var)
        routing.AddVariableMinimizedByFinalizer(end_var)

        if problem.depot_service_time_minutes > 0 and problem.depot_gate_limit > 0:
            service_start = solver.IntVar(
                shift_start,
                max(shift_start, shift_end - problem.depot_service_time_minutes),
                f"depot_service_start_{vehicle_id}",
            )
            service_end = solver.IntVar(
                shift_start + problem.depot_service_time_minutes,
                shift_end,
                f"depot_service_end_{vehicle_id}",
            )
            routing.AddVariableMinimizedByFinalizer(service_start)
            solver.Add(service_end == service_start + problem.depot_service_time_minutes)
            service_interval = solver.FixedDurationIntervalVar(
                service_start,
                problem.depot_service_time_minutes,
                routing.ActiveVehicleVar(vehicle_id),
                f"depot_service_{vehicle_id}",
            )
            solver.Add(service_interval.SafeEndExpr(shift_start) == start_var)
            register_depot_operation_window(
                routing.ActiveVehicleVar(vehicle_id),
                service_start,
                service_end,
                f"depot_operation_start_{vehicle_id}",
            )
            depot_service_intervals.append(
                service_interval
            )
            depot_service_demands.append(1)

        if problem.config.hard_constraints.max_vehicle_working_time:
            end_var.SetRange(shift_start, working_time_limit)
        else:
            end_var.SetRange(shift_start, horizon)
            if (
                problem.config.soft_constraints.allow_overtime
                or problem.config.soft_constraints.max_vehicle_working_time
            ):
                dimension.SetCumulVarSoftUpperBound(
                    routing.End(vehicle_id),
                    working_time_limit,
                    int(problem.config.penalties.overtime_penalty_per_minute),
                )

        if problem.config.hard_constraints.max_route_duration and problem.config.max_route_duration_minutes:
            end_var.SetMax(shift_start + problem.config.max_route_duration_minutes)
        elif (
            problem.config.soft_constraints.allow_overtime
            or problem.config.soft_constraints.max_route_duration
        ) and problem.config.max_route_duration_minutes:
            dimension.SetCumulVarSoftUpperBound(
                routing.End(vehicle_id),
                shift_start + problem.config.max_route_duration_minutes,
                int(problem.config.penalties.overtime_penalty_per_minute),
            )

    for shipment in problem.shipments:
        index = manager.NodeToIndex(shipment.node_index)
        cumul = dimension.CumulVar(index)
        solver.Add(cumul >= shipment.time_window_start)
        hard_upper_bounds: list[int] = []
        if problem.config.hard_constraints.time_window:
            hard_upper_bounds.append(shipment.time_window_end)
        if problem.config.hard_constraints.priority_eta and shipment.priority_eta_minutes is not None:
            hard_upper_bounds.append(shipment.priority_eta_minutes)
        if hard_upper_bounds:
            solver.Add(cumul <= min(hard_upper_bounds))
        else:
            cumul.SetMax(horizon)
        if (
            not problem.config.hard_constraints.time_window
            and problem.config.soft_constraints.time_window
        ):
            dimension.SetCumulVarSoftUpperBound(
                index,
                shipment.time_window_end,
                int(problem.config.penalties.late_arrival_penalty_per_minute),
            )
        if (
            problem.config.soft_constraints.priority_eta
            and not problem.config.hard_constraints.priority_eta
            and shipment.priority_eta_minutes is not None
        ):
            penalty = max(0, int(round(problem.config.penalties.priority_eta_penalty_per_minute)))
            if penalty > 0:
                priority_eta_lateness = solver.IntVar(
                    0,
                    horizon,
                    f"priority_eta_lateness_{shipment.node_index}",
                )
                solver.Add(
                    priority_eta_lateness == solver.Max(cumul - shipment.priority_eta_minutes, 0)
                )
                extra_objective_vars.append(priority_eta_lateness)
                extra_objective_weights.append(penalty)
    for reload_node in problem.reload_nodes:
        index = manager.NodeToIndex(reload_node.node_index)
        dimension.CumulVar(index).SetRange(reload_node.time_window_start, reload_node.time_window_end)
        if problem.depot_service_time_minutes > 0 and problem.depot_gate_limit > 0:
            reload_service_start = solver.IntVar(
                reload_node.time_window_start,
                reload_node.time_window_end,
                f"reload_service_start_{reload_node.node_index}",
            )
            reload_service_end = solver.IntVar(
                reload_node.time_window_start + problem.depot_service_time_minutes,
                min(horizon, reload_node.time_window_end + problem.depot_service_time_minutes),
                f"reload_service_end_{reload_node.node_index}",
            )
            routing.AddVariableMinimizedByFinalizer(reload_service_start)
            solver.Add(reload_service_start == dimension.CumulVar(index))
            solver.Add(reload_service_end == reload_service_start + problem.depot_service_time_minutes)
            reload_interval = solver.FixedDurationIntervalVar(
                reload_service_start,
                problem.depot_service_time_minutes,
                routing.ActiveVar(index),
                f"reload_service_{reload_node.node_index}",
            )
            register_depot_operation_window(
                routing.ActiveVar(index),
                reload_service_start,
                reload_service_end,
                f"depot_operation_reload_{reload_node.node_index}",
            )
            depot_service_intervals.append(reload_interval)
            depot_service_demands.append(1)
    if depot_service_intervals:
        solver.Add(
            solver.Cumulative(
                depot_service_intervals,
                depot_service_demands,
                problem.depot_gate_limit,
                "depot_gate_capacity",
            )
        )
    if depot_operation_start_vars:
        depot_operation_active_count = solver.IntVar(
            0,
            len(depot_operation_active_vars),
            "depot_operation_active_count",
        )
        earliest_start = solver.IntVar(0, horizon, "depot_operation_earliest_start")
        latest_end = solver.IntVar(0, horizon, "depot_operation_latest_end")
        solver.Add(depot_operation_active_count == solver.Sum(depot_operation_active_vars))
        solver.Add(solver.MinEquality(depot_operation_start_vars, earliest_start))
        solver.Add(solver.MaxEquality(depot_operation_end_vars, latest_end))
        if problem.config.hard_constraints.depot_operation_window:
            solver.Add(earliest_start >= problem.depot_operation_window_start)
            solver.Add(latest_end <= problem.depot_operation_window_end)
        elif problem.config.soft_constraints.depot_operation_window:
            penalty = max(0, int(round(problem.config.penalties.depot_operation_window_penalty_per_minute)))
            if penalty > 0:
                early_violation = solver.IntVar(0, horizon, "depot_operation_early_violation")
                late_violation = solver.IntVar(0, horizon, "depot_operation_late_violation")
                solver.Add(
                    early_violation
                    == solver.Max(problem.depot_operation_window_start - earliest_start, 0)
                )
                solver.Add(
                    late_violation
                    == solver.Max(latest_end - problem.depot_operation_window_end, 0)
                )
                extra_objective_vars.extend([early_violation, late_violation])
                extra_objective_weights.extend([penalty, penalty])
    return TimeConstraintArtifacts(
        dimension=dimension,
        extra_objective_vars=extra_objective_vars,
        extra_objective_weights=extra_objective_weights,
    )


def apply_vehicle_compatibility(
    routing: pywrapcp.RoutingModel,
    manager: pywrapcp.RoutingIndexManager,
    problem: PreprocessedProblem,
) -> None:
    """Restrict shipment nodes to allowed vehicles."""

    for shipment in problem.shipments:
        index = manager.NodeToIndex(shipment.node_index)
        routing.SetAllowedVehiclesForIndex(shipment.allowed_vehicle_indices, index)
    for reload_node in problem.reload_nodes:
        index = manager.NodeToIndex(reload_node.node_index)
        routing.SetAllowedVehiclesForIndex(reload_node.allowed_vehicle_indices, index)


def apply_optional_visits(
    routing: pywrapcp.RoutingModel,
    manager: pywrapcp.RoutingIndexManager,
    problem: PreprocessedProblem,
) -> None:
    """Allow solver to drop visits when configured."""

    if not problem.config.soft_constraints.allow_unserved_orders:
        for reload_node in problem.reload_nodes:
            routing.AddDisjunction([manager.NodeToIndex(reload_node.node_index)], 0)
        return
    penalty = int(problem.config.penalties.unserved_order_penalty)
    for shipment in problem.shipments:
        routing.AddDisjunction([manager.NodeToIndex(shipment.node_index)], penalty)
    for reload_node in problem.reload_nodes:
        routing.AddDisjunction([manager.NodeToIndex(reload_node.node_index)], 0)
