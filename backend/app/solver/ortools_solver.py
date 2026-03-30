"""OR-Tools routing solver orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.models import schemas
from app.services.preprocessing_service import PreprocessedProblem
from app.solver.model_builder import BuiltModel, build_routing_model_with_options

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


class OrToolsSolver:
    """Solve the prepared routing problem using OR-Tools."""

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
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.time_limit.seconds = max(
            1,
            int(
                time_limit_seconds
                if time_limit_seconds is not None
                else problem.config.solver_options.max_solver_seconds
            ),
        )
        search_parameters.first_solution_strategy = FIRST_STRATEGIES.get(
            problem.config.solver_options.first_solution_strategy,
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
        )
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
    def _service_level_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.minimize_unserved_orders = True
        config.minimize_truck_count = False
        config.minimize_distance = False
        config.minimize_time = False
        config.minimize_depot_operation_time = False
        config.objective_priority = [
            "minimize_unserved_orders",
            "minimize_truck_count",
            "minimize_distance",
            "minimize_time",
            "minimize_depot_operation_time",
        ]
        config.soft_constraints = config.soft_constraints.model_copy(
            update={
                "time_window": False,
                "allow_overtime": False,
                "depot_operation_window": False,
                "max_route_duration": False,
                "max_vehicle_working_time": False,
                "max_total_distance_per_vehicle": False,
            }
        )
        return config

    @staticmethod
    def _quality_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.minimize_unserved_orders = True
        config.minimize_truck_count = False
        config.minimize_distance = False
        config.minimize_time = False
        config.minimize_depot_operation_time = False
        config.objective_priority = [
            "minimize_unserved_orders",
            "minimize_time",
            "minimize_distance",
            "minimize_truck_count",
            "minimize_depot_operation_time",
        ]
        return config

    @staticmethod
    def _best_effort_config(problem: PreprocessedProblem) -> schemas.OptimizationConfig:
        config = problem.config.model_copy(deep=True)
        config.soft_constraints = config.soft_constraints.model_copy(update={"allow_unserved_orders": True})
        config.minimize_unserved_orders = True
        config.objective_priority = [
            "minimize_unserved_orders",
            *[item for item in config.objective_priority if item != "minimize_unserved_orders"],
        ]
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
    def _count_unserved_shipments(
        problem: PreprocessedProblem,
        built_model: BuiltModel,
        assignment: pywrapcp.Assignment,
    ) -> int:
        routing = built_model.routing
        manager = built_model.manager
        if not all(
            hasattr(routing, attr)
            for attr in ("Start", "IsEnd", "NextVar")
        ) or not hasattr(manager, "IndexToNode"):
            return 0
        visited_shipments: set[str] = set()
        for vehicle_id in range(len(problem.trucks)):
            index = routing.Start(vehicle_id)
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                node_detail = problem.get_node(node)
                if node_detail is not None and node_detail.node_kind == "shipment":
                    visited_shipments.add(node_detail.order_id)
                index = assignment.Value(routing.NextVar(index))
        return len([shipment for shipment in problem.shipments if shipment.order_id not in visited_shipments])

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
    ) -> StageSolveResult:
        built_model = build_routing_model_with_options(
            problem,
            include_soft_priority_eta_objective=include_soft_priority_eta_objective,
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
    ) -> StageSolveResult:
        built_model = build_routing_model_with_options(
            problem,
            include_soft_priority_eta_objective=include_soft_priority_eta_objective,
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

    def _run_multistage_pipeline(
        self,
        problem: PreprocessedProblem,
        *,
        started: float,
        best_effort_prefix: str | None = None,
    ) -> SolverOutput:
        service_problem = self._problem_with_config(problem, self._service_level_config(problem))
        quality_problem = self._problem_with_config(problem, self._quality_config(problem))
        service_seconds, repair_seconds, quality_seconds, full_seconds = self._allocate_stage_budgets(
            problem.config.solver_options.max_solver_seconds,
            include_repair=problem.config.soft_constraints.allow_unserved_orders,
        )

        service_result = self._solve_stage(
            service_problem,
            time_limit_seconds=service_seconds,
            include_soft_priority_eta_objective=False,
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

        if quality_seconds > 0:
            quality_result = self._refine_stage(
                quality_problem,
                seed_model=best_model,
                seed_assignment=best_assignment,
                time_limit_seconds=quality_seconds,
                include_soft_priority_eta_objective=quality_problem.config.soft_constraints.priority_eta,
            )
            if quality_result.assignment is not None:
                quality_unserved = self._count_unserved_shipments(
                    quality_problem,
                    quality_result.built_model,
                    quality_result.assignment,
                )
                if quality_unserved <= best_unserved:
                    best_model = quality_result.built_model
                    best_assignment = quality_result.assignment
                    best_unserved = quality_unserved
                    quality_refined = True

        if full_seconds > 0:
            full_result = self._refine_stage(
                problem,
                seed_model=best_model,
                seed_assignment=best_assignment,
                time_limit_seconds=full_seconds,
                include_soft_priority_eta_objective=problem.config.soft_constraints.priority_eta,
            )
            if full_result.assignment is not None:
                full_unserved = self._count_unserved_shipments(
                    problem,
                    full_result.built_model,
                    full_result.assignment,
                )
                if full_unserved <= best_unserved:
                    best_model = full_result.built_model
                    best_assignment = full_result.assignment
                    best_unserved = full_unserved
                    cost_refined = True

        runtime = time.perf_counter() - started
        message_prefix = f"{best_effort_prefix} " if best_effort_prefix else ""
        if best_unserved == 0:
            message = f"{message_prefix}Optimization finished after service-level, quality, and cost refinement.".strip()
        elif repaired or quality_refined or cost_refined:
            message = (
                f"{message_prefix}Optimization finished with best-effort partial routes after "
                "service-level repair and quality refinement."
            ).strip()
        else:
            message = f"{message_prefix}Optimization finished with the best service-level solution found.".strip()
        return SolverOutput(
            built_model=best_model,
            assignment=best_assignment,
            runtime_seconds=runtime,
            message=message,
            search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
        )

    def solve(self, problem: PreprocessedProblem) -> SolverOutput:
        started = time.perf_counter()
        logger.info("Running OR-Tools with %s shipments and %s vehicles", len(problem.shipments), len(problem.trucks))

        output = self._run_multistage_pipeline(problem, started=started)
        if output.assignment is not None:
            return output

        if (
            not problem.config.soft_constraints.allow_unserved_orders
            and output.search_status == routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT
        ):
            logger.info(
                "Strict full-feasible solve timed out; retrying scenario %s with best-effort fallback.",
                problem.dispatch_date,
            )
            best_effort_problem = self._problem_with_config(problem, self._best_effort_config(problem))
            best_effort_output = self._run_multistage_pipeline(
                best_effort_problem,
                started=started,
                best_effort_prefix=(
                    "Full-feasible solve hit the time limit; returning best-effort partial solution."
                ),
            )
            if best_effort_output.assignment is not None:
                return best_effort_output

        return output
