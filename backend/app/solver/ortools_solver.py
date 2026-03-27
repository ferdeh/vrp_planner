"""OR-Tools routing solver orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.services.preprocessing_service import PreprocessedProblem
from app.solver.model_builder import BuiltModel, build_routing_model

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


class OrToolsSolver:
    """Solve the prepared routing problem using OR-Tools."""

    def solve(self, problem: PreprocessedProblem) -> SolverOutput:
        started = time.perf_counter()
        built_model = build_routing_model(problem)
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.time_limit.seconds = problem.config.solver_options.max_solver_seconds
        search_parameters.first_solution_strategy = FIRST_STRATEGIES.get(
            problem.config.solver_options.first_solution_strategy,
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
        )
        search_parameters.local_search_metaheuristic = LOCAL_SEARCH.get(
            problem.config.solver_options.local_search_metaheuristic,
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH,
        )
        search_parameters.log_search = False
        built_model.routing.CloseModelWithParameters(search_parameters)
        if built_model.extra_objective_vars and built_model.extra_objective_weights:
            built_model.routing.AddSearchMonitor(
                built_model.routing.solver().WeightedMinimize(
                    [built_model.routing.CostVar(), *built_model.extra_objective_vars],
                    [1, *built_model.extra_objective_weights],
                    1,
                )
            )

        logger.info("Running OR-Tools with %s shipments and %s vehicles", len(problem.shipments), len(problem.trucks))
        assignment = built_model.routing.SolveWithParameters(search_parameters)
        runtime = time.perf_counter() - started
        message = "Optimization finished."
        if assignment is None:
            message = "No feasible solution found by solver."
        return SolverOutput(built_model=built_model, assignment=assignment, runtime_seconds=runtime, message=message)
