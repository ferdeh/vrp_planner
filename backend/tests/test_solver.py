"""Tests for solver behavior."""

from __future__ import annotations

from types import SimpleNamespace

from ortools.constraint_solver import routing_enums_pb2

from app.models import schemas
from app.services import master_data_client as master_data_module
from app.services.preprocessing_service import PreprocessedProblem, PreprocessingService, RouteNode
from app.services.result_service import ResultService
from app.solver.objective import effective_unserved_penalty, objective_priority_scale, transit_cost
from app.solver import ortools_solver as ortools_solver_module
from app.solver.ortools_solver import OrToolsSolver
from app.utils.time_utils import hhmm_to_minutes


def test_solver_returns_feasible_basic_case(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = OrToolsSolver().solve(problem)
    result = ResultService().build_response("00000000-0000-0000-0000-000000000001", problem, solver_output)

    assert solver_output.assignment is not None
    assert result.status in {"feasible", "partial"}
    assert result.total_delivered_demand > 0
    assert result.active_truck_count >= 1


def test_solver_returns_infeasible_when_spbu_node_time_window_impossible(configured_modules, sample_payload, monkeypatch):
    monkeypatch.setattr(
        master_data_module,
        "MOCK_SPBU",
        [
            {
                "spbu_id": "SPBU001",
                "name": "SPBU A",
                "lat": -6.11,
                "lng": 106.71,
                "time_window_start": "08:00",
                "time_window_end": "08:05",
                "truck_category": 4,
                "allowed_truck_types": ["SMALL", "MEDIUM", "LARGE"],
            },
            {
                "spbu_id": "SPBU002",
                "name": "SPBU B",
                "lat": -6.12,
                "lng": 106.72,
                "time_window_start": "08:00",
                "time_window_end": "08:05",
                "truck_category": 4,
                "allowed_truck_types": ["SMALL", "MEDIUM", "LARGE"],
            },
        ],
    )
    sample_payload["available_trucks"][0]["shift_start"] = "06:00"
    sample_payload["available_trucks"][0]["shift_end"] = "06:05"
    sample_payload["available_trucks"][1]["shift_start"] = "06:00"
    sample_payload["available_trucks"][1]["shift_end"] = "06:05"
    sample_payload["optimization_config"]["soft_constraints"]["allow_unserved_orders"] = False
    payload = schemas.OptimizationRequest.model_validate(sample_payload)

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = OrToolsSolver().solve(problem)

    assert solver_output.assignment is None


def test_solver_returns_infeasible_when_priority_eta_is_hard_and_before_spbu_window(
    configured_modules,
    sample_payload,
):
    sample_payload["orders"] = [sample_payload["orders"][0]]
    sample_payload["orders"][0]["demand_kl"] = 8
    sample_payload["orders"][0]["priority"] = True
    sample_payload["orders"][0]["eta"] = "07:00"
    sample_payload["optimization_config"]["soft_constraints"]["allow_unserved_orders"] = False
    payload = schemas.OptimizationRequest.model_validate(sample_payload)

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = OrToolsSolver().solve(problem)
    result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000102",
        problem,
        solver_output,
    )

    assert solver_output.assignment is None
    assert result.unserved_orders
    assert any(
        "SPBU Priority hard aktif" in detail
        for detail in result.unserved_orders[0].constraint_details
    )


def test_solver_returns_infeasible_when_priority_eta_is_hard_even_if_unserved_is_allowed(
    configured_modules,
    sample_payload,
):
    sample_payload["orders"] = [sample_payload["orders"][0]]
    sample_payload["orders"][0]["demand_kl"] = 8
    sample_payload["orders"][0]["priority"] = True
    sample_payload["orders"][0]["eta"] = "07:00"
    sample_payload["optimization_config"]["soft_constraints"]["allow_unserved_orders"] = True
    payload = schemas.OptimizationRequest.model_validate(sample_payload)

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = OrToolsSolver().solve(problem)

    assert solver_output.assignment is None


def test_solver_adds_priority_eta_penalty_when_priority_eta_is_soft(
    configured_modules,
    sample_payload,
):
    sample_payload["orders"] = [sample_payload["orders"][0]]
    sample_payload["orders"][0]["demand_kl"] = 8
    sample_payload["orders"][0]["priority"] = True
    sample_payload["orders"][0]["eta"] = "07:00"
    sample_payload["optimization_config"]["hard_constraints"]["priority_eta"] = False
    sample_payload["optimization_config"]["soft_constraints"]["priority_eta"] = True
    sample_payload["optimization_config"]["penalties"]["priority_eta_penalty_per_minute"] = 250
    payload = schemas.OptimizationRequest.model_validate(sample_payload)

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = OrToolsSolver().solve(problem)
    result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000099",
        problem,
        solver_output,
    )

    assert solver_output.assignment is not None
    assert result.status in {"feasible", "partial"}
    assert result.total_penalty >= 250
    assert result.total_cost >= result.total_penalty


def test_solver_keeps_priority_order_served_when_priority_eta_is_soft_and_unserved_penalty_is_low(
    configured_modules,
    sample_payload,
):
    sample_payload["orders"] = [sample_payload["orders"][0]]
    sample_payload["orders"][0]["demand_kl"] = 8
    sample_payload["orders"][0]["priority"] = True
    sample_payload["orders"][0]["eta"] = "07:00"
    sample_payload["optimization_config"]["hard_constraints"]["priority_eta"] = False
    sample_payload["optimization_config"]["soft_constraints"]["priority_eta"] = True
    sample_payload["optimization_config"]["soft_constraints"]["allow_unserved_orders"] = True
    sample_payload["optimization_config"]["penalties"]["unserved_order_penalty"] = 1
    sample_payload["optimization_config"]["penalties"]["priority_eta_penalty_per_minute"] = 250
    payload = schemas.OptimizationRequest.model_validate(sample_payload)

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = OrToolsSolver().solve(problem)
    result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000100",
        problem,
        solver_output,
    )

    assert solver_output.assignment is not None
    assert result.total_unserved_orders == 0
    assert result.total_delivered_demand == 8
    assert result.total_penalty >= 250


def test_solver_output_marks_timeout_when_routing_hits_time_limit(
    configured_modules,
    sample_payload,
    monkeypatch,
):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)

    class FakeRouting:
        def CloseModelWithParameters(self, _params):
            return None

        def SolveWithParameters(self, _params):
            return None

        def status(self):
            return routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT

    monkeypatch.setattr(
        ortools_solver_module,
        "build_routing_model_with_options",
        lambda _problem, include_soft_priority_eta_objective=True: SimpleNamespace(
            routing=FakeRouting(),
            manager=None,
            time_dimension=None,
            distance_dimension=None,
            capacity_dimension=None,
            extra_objective_vars=[],
            extra_objective_weights=[],
        ),
    )

    solver_output = OrToolsSolver().solve(problem)

    assert solver_output.assignment is None
    assert solver_output.search_status == routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT
    assert solver_output.message == "Solver reached the time limit before finding a feasible solution."


def test_solver_keeps_service_level_solution_when_quality_refinement_times_out(
    configured_modules,
    sample_payload,
    monkeypatch,
):
    sample_payload["optimization_config"]["hard_constraints"]["priority_eta"] = False
    sample_payload["optimization_config"]["soft_constraints"]["priority_eta"] = True
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)

    base_assignment = object()
    refinement_seed = object()

    class FakeSolver:
        def Assignment(self):
            return refinement_seed

        def WeightedMinimize(self, *_args):
            return None

    class StageOneRouting:
        def __init__(self):
            self._solver = FakeSolver()

        def CloseModelWithParameters(self, _params):
            return None

        def AddSearchMonitor(self, _monitor):
            return None

        def solver(self):
            return self._solver

        def SolveWithParameters(self, _params):
            return base_assignment

        def status(self):
            return routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS

        def CostVar(self):
            return None

    class RefinementRouting:
        def __init__(self):
            self._solver = FakeSolver()
            self.seed_captured = None
            self.source_assignment_captured = None

        def CloseModelWithParameters(self, _params):
            return None

        def AddSearchMonitor(self, _monitor):
            return None

        def solver(self):
            return self._solver

        def SetAssignmentFromOtherModelAssignment(self, target_assignment, _source_model, source_assignment):
            self.seed_captured = target_assignment
            self.source_assignment_captured = source_assignment

        def SolveFromAssignmentWithParameters(self, assignment, _params, solutions=None):
            self.seed_captured = assignment
            return None

        def status(self):
            return routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT

        def CostVar(self):
            return None

    stage_one_model = SimpleNamespace(
        routing=StageOneRouting(),
        manager="stage-one-manager",
        time_dimension=None,
        distance_dimension=None,
        capacity_dimension=None,
        extra_objective_vars=[],
        extra_objective_weights=[],
    )
    quality_model = SimpleNamespace(
        routing=RefinementRouting(),
        manager="quality-manager",
        time_dimension=None,
        distance_dimension=None,
        capacity_dimension=None,
        extra_objective_vars=["priority"],
        extra_objective_weights=[1],
    )
    full_model = SimpleNamespace(
        routing=RefinementRouting(),
        manager="full-manager",
        time_dimension=None,
        distance_dimension=None,
        capacity_dimension=None,
        extra_objective_vars=["priority"],
        extra_objective_weights=[1],
    )
    models = [stage_one_model, quality_model, full_model]

    monkeypatch.setattr(
        ortools_solver_module,
        "build_routing_model_with_options",
        lambda _problem, include_soft_priority_eta_objective=True: models.pop(0),
    )

    solver_output = OrToolsSolver().solve(problem)

    assert solver_output.assignment is base_assignment
    assert solver_output.built_model is stage_one_model
    assert solver_output.search_status == routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS
    assert "strict full-service" in solver_output.message
    assert quality_model.routing.seed_captured is refinement_seed
    assert quality_model.routing.source_assignment_captured is base_assignment
    assert full_model.routing.seed_captured is None
    assert full_model.routing.source_assignment_captured is None


def test_solver_returns_best_effort_partial_when_strict_full_feasible_times_out(
    configured_modules,
    sample_payload,
    monkeypatch,
):
    sample_payload["optimization_config"]["soft_constraints"]["allow_unserved_orders"] = True
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)

    strict_timeout = ortools_solver_module.SolverOutput(
        built_model=SimpleNamespace(
            routing=None,
            manager=None,
            time_dimension=None,
            distance_dimension=None,
            capacity_dimension=None,
            extra_objective_vars=[],
            extra_objective_weights=[],
        ),
        assignment=None,
        runtime_seconds=1.0,
        message="Solver reached the time limit before finding a feasible solution.",
        search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT,
    )
    best_effort_assignment = object()
    best_effort_result = ortools_solver_module.SolverOutput(
        built_model=SimpleNamespace(
            routing=None,
            manager=None,
            time_dimension=None,
            distance_dimension=None,
            capacity_dimension=None,
            extra_objective_vars=[],
            extra_objective_weights=[],
        ),
        assignment=best_effort_assignment,
        runtime_seconds=2.0,
        message="Full-feasible solve hit the time limit; returning best-effort partial solution.",
        search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
    )
    prefixes: list[str | None] = []

    def fake_full_service(self, _problem, *, started, total_seconds):
        prefixes.append(None)
        return strict_timeout

    def fake_best_effort(self, _problem, *, started, total_seconds, best_effort_prefix=None):
        prefixes.append(best_effort_prefix)
        return best_effort_result

    monkeypatch.setattr(OrToolsSolver, "_run_full_service_pipeline", fake_full_service)
    monkeypatch.setattr(OrToolsSolver, "_run_best_effort_pipeline", fake_best_effort)

    solver_output = OrToolsSolver().solve(problem)

    assert solver_output.assignment is best_effort_assignment
    assert solver_output.search_status == routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS
    assert prefixes == [None, "Strict full-service solve failed; returning best-effort partial solution."]


def test_result_status_becomes_timeout_when_solver_times_out(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = ortools_solver_module.SolverOutput(
        built_model=SimpleNamespace(
            routing=None,
            manager=None,
            time_dimension=None,
            distance_dimension=None,
            capacity_dimension=None,
            extra_objective_vars=[],
            extra_objective_weights=[],
        ),
        assignment=None,
        runtime_seconds=30.0,
        message="Solver reached the time limit before finding a feasible solution.",
        search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT,
    )

    result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000101",
        problem,
        solver_output,
    )

    assert result.status == "timeout"
    assert result.message == "Solver reached the time limit before finding a feasible solution."
    assert result.total_unserved_orders == len(payload.orders)


def test_solver_adds_depot_service_time_per_truck(configured_modules, sample_payload):
    base_payload = schemas.OptimizationRequest.model_validate(sample_payload)
    base_payload.orders = [base_payload.orders[0].model_copy(update={"demand_kl": 8})]
    base_payload.available_trucks = [base_payload.available_trucks[0]]
    base_payload.depot_service_time_minutes = 0
    base_payload.optimization_config.minimize_depot_operation_time = False

    with_service_payload = base_payload.model_copy(deep=True)
    with_service_payload.depot_service_time_minutes = 20

    base_problem = PreprocessingService().preprocess(base_payload, base_payload.optimization_config)
    with_service_problem = PreprocessingService().preprocess(
        with_service_payload,
        with_service_payload.optimization_config,
    )

    base_result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000002",
        base_problem,
        OrToolsSolver().solve(base_problem),
    )
    with_service_result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000003",
        with_service_problem,
        OrToolsSolver().solve(with_service_problem),
    )

    assert (
        hhmm_to_minutes(with_service_result.route_details[0].origin_etd)
        - hhmm_to_minutes(base_result.route_details[0].origin_etd)
        == 20
    )
    assert with_service_result.route_details[0].origin_service_start == base_result.route_details[0].origin_service_start
    assert with_service_result.route_details[0].depot_service_time_minutes == 20
    assert with_service_result.total_depot_operation_time_minutes == 20
    assert with_service_result.depot_operation_start == with_service_result.route_details[0].origin_service_start
    assert with_service_result.depot_operation_end == with_service_result.route_details[0].origin_etd


def test_minimize_depot_operation_time_does_not_add_reload_cost_to_transit_arcs(sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    truck = payload.available_trucks[0]
    config = payload.optimization_config.model_copy(deep=True)
    config.minimize_distance = False
    config.minimize_time = False
    config.minimize_depot_operation_time = True
    config.penalties.depot_operation_time_weight = 99

    no_reload_cost = transit_cost(
        distance_km=0,
        travel_minutes=0,
        truck=truck,
        config=config,
    )
    reload_cost = transit_cost(
        distance_km=0,
        travel_minutes=0,
        truck=truck,
        config=config,
    )

    assert no_reload_cost == 0
    assert reload_cost == 0


def test_objective_priority_scales_follow_user_order(sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    config = payload.optimization_config.model_copy(deep=True)
    config.minimize_truck_count = True
    config.minimize_distance = True
    config.minimize_time = True
    config.minimize_depot_operation_time = True
    config.objective_priority = [
        "minimize_distance",
        "minimize_time",
        "minimize_truck_count",
        "minimize_depot_operation_time",
    ]

    assert objective_priority_scale(config, "minimize_distance") > objective_priority_scale(
        config,
        "minimize_time",
    )
    assert objective_priority_scale(config, "minimize_time") > objective_priority_scale(
        config,
        "minimize_truck_count",
    )
    assert effective_unserved_penalty(config) == int(config.penalties.unserved_order_penalty)


def test_preprocessing_limits_reload_nodes_to_capacity_deficit(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    payload.orders.append(
        schemas.OrderInput(
            order_id="ORD003",
            spbu_id="SPBU001",
            product_type="PERTALITE",
            demand_kl=8,
            priority=False,
            eta=None,
            service_time_minutes=30,
            time_window_start="08:00",
            time_window_end="15:00",
        )
    )

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)

    assert problem.total_demand == 32
    assert sum(truck.capacity_kl for truck in problem.trucks) == 24
    assert len(problem.reload_nodes) == 1


def test_preprocessing_builds_group_specific_reload_nodes(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    payload.available_trucks = [
        payload.available_trucks[0].model_copy(
            update={
                "truck_id": "TRK001",
                "capacity_kl": 8,
                "compartments": [schemas.TruckCompartment(compartment_id="1", capacity_kl=8)],
            }
        ),
        payload.available_trucks[1].model_copy(
            update={
                "truck_id": "TRK002",
                "capacity_kl": 16,
                "compartments": [
                    schemas.TruckCompartment(compartment_id="1", capacity_kl=8),
                    schemas.TruckCompartment(compartment_id="2", capacity_kl=8),
                ],
            }
        ),
    ]
    payload.orders = [
        schemas.OrderInput(
            order_id=f"ORD{index:03d}",
            spbu_id="SPBU001" if index % 2 else "SPBU002",
            product_type="PERTALITE",
            demand_kl=8,
            priority=False,
            eta=None,
            service_time_minutes=30,
            time_window_start="08:00",
            time_window_end="15:00",
        )
        for index in range(1, 6)
    ]

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    grouped_reload_nodes = {
        (tuple(node.allowed_vehicle_indices), node.reload_capacity_kl, node.reload_compartment_count)
        for node in problem.reload_nodes
    }

    assert ((0,), 8.0, 1) in grouped_reload_nodes
    assert ((1,), 16.0, 2) in grouped_reload_nodes


def test_solver_uses_insertion_seed_when_multi_trip_reload_nodes_exist(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    payload.orders.append(
        schemas.OrderInput(
            order_id="ORD003",
            spbu_id="SPBU001",
            product_type="PERTALITE",
            demand_kl=8,
            priority=False,
            eta=None,
            service_time_minutes=30,
            time_window_start="08:00",
            time_window_end="15:00",
        )
    )

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)

    assert len(problem.reload_nodes) == 1
    assert problem.config.solver_options.first_solution_strategy == "PATH_CHEAPEST_ARC"
    assert (
        OrToolsSolver._resolve_first_solution_strategy(problem)
        == routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )


def test_solver_extends_time_budget_for_heavy_multi_trip_problem(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    payload.orders = [
        schemas.OrderInput(
            order_id=f"ORD{index:03d}",
            spbu_id="SPBU001" if index % 2 else "SPBU002",
            product_type="PERTALITE",
            demand_kl=8,
            priority=False,
            eta=None,
            service_time_minutes=30,
            time_window_start="08:00",
            time_window_end="15:00",
        )
        for index in range(1, 13)
    ]
    payload.optimization_config.solver_options.max_solver_seconds = 30

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)

    assert OrToolsSolver._is_heavy_multi_trip_problem(problem) is True
    assert OrToolsSolver._effective_time_limit_seconds(problem, 30) == 45


def test_solver_stage_time_budget_remains_explicit_for_heavy_multi_trip_problem(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    payload.orders = [
        schemas.OrderInput(
            order_id=f"ORD{index:03d}",
            spbu_id="SPBU001" if index % 2 else "SPBU002",
            product_type="PERTALITE",
            demand_kl=8,
            priority=False,
            eta=None,
            service_time_minutes=30,
            time_window_start="08:00",
            time_window_end="15:00",
        )
        for index in range(1, 13)
    ]

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    params = OrToolsSolver._build_search_parameters(problem, time_limit_seconds=7)

    assert OrToolsSolver._is_heavy_multi_trip_problem(problem) is True
    assert params.time_limit.seconds == 7


def test_solver_keeps_requested_time_budget_for_small_multi_trip_problem(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    payload.orders.append(
        schemas.OrderInput(
            order_id="ORD003",
            spbu_id="SPBU001",
            product_type="PERTALITE",
            demand_kl=8,
            priority=False,
            eta=None,
            service_time_minutes=30,
            time_window_start="08:00",
            time_window_end="15:00",
        )
    )
    payload.optimization_config.solver_options.max_solver_seconds = 30

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)

    assert OrToolsSolver._is_heavy_multi_trip_problem(problem) is False
    assert OrToolsSolver._effective_time_limit_seconds(problem, 30) == 30


def test_targeted_cleanup_problem_prioritizes_low_working_time_trucks(sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    trucks = [
        payload.available_trucks[0].model_copy(update={"truck_id": "TRK001", "shift_end": "18:00"}),
        payload.available_trucks[1].model_copy(update={"truck_id": "TRK002", "shift_end": "18:00"}),
        payload.available_trucks[0].model_copy(update={"truck_id": "TRK003", "shift_end": "18:00"}),
    ]
    shipments = [
        RouteNode(
            node_index=1,
            node_kind="shipment",
            order_id="ORD-SERVED",
            parent_order_id="ORD-SERVED",
            spbu_id="SPBU001",
            product_type="PERTALITE",
            demand_kl=8,
            service_time_minutes=30,
            time_window_start=0,
            time_window_end=1439,
            allowed_vehicle_indices=[2],
            matrix_node_name="SPBU001",
        ),
        RouteNode(
            node_index=2,
            node_kind="shipment",
            order_id="ORD-UNSERVED",
            parent_order_id="ORD-UNSERVED",
            spbu_id="SPBU002",
            product_type="PERTALITE",
            demand_kl=8,
            service_time_minutes=30,
            time_window_start=0,
            time_window_end=1439,
            allowed_vehicle_indices=[0, 1, 2],
            matrix_node_name="SPBU002",
        ),
    ]
    problem = PreprocessedProblem(
        depot_id="DPT001",
        depot_name="Depot",
        depot_gate_limit=3,
        depot_operation_window_start=0,
        depot_operation_window_end=1439,
        dispatch_date="2026-04-10",
        depot_service_time_minutes=30,
        config=payload.optimization_config,
        notes=[],
        route_nodes=shipments,
        preassigned_unserved=[],
        orders=payload.orders,
        trucks=trucks,
        spbu_map={},
        time_matrix=[[0]],
        distance_matrix=[[0]],
        matrix_positions={"DEPOT": 0},
    )

    class FakeRouting:
        starts = {0: 100, 1: 110, 2: 120}
        ends = {0: 101, 1: 111, 2: 121}

        def Start(self, vehicle_id):
            return self.starts[vehicle_id]

        def End(self, vehicle_id):
            return self.ends[vehicle_id]

        def IsEnd(self, index):
            return index in set(self.ends.values())

        def NextVar(self, index):
            return ("next", index)

    class FakeManager:
        def IndexToNode(self, index):
            return {
                100: 0,
                101: 0,
                110: 0,
                111: 0,
                120: 0,
                121: 0,
                1: 1,
                2: 2,
            }.get(index, 0)

    class FakeTimeDimension:
        def CumulVar(self, index):
            return ("time", index)

    class FakeAssignment:
        def Value(self, value):
            kind, index = value
            if kind == "next":
                return {
                    100: 101,
                    110: 111,
                    120: 1,
                    1: 121,
                }[index]
            return {
                100: 360,
                101: 480,
                110: 360,
                111: 420,
                120: 360,
                121: 660,
            }[index]

    built_model = SimpleNamespace(
        routing=FakeRouting(),
        manager=FakeManager(),
        time_dimension=FakeTimeDimension(),
        distance_dimension=None,
        capacity_dimension=None,
        extra_objective_vars=[],
        extra_objective_weights=[],
    )

    targeted = OrToolsSolver._build_targeted_cleanup_problem(
        problem,
        built_model,
        FakeAssignment(),
        max_candidates_per_shipment=1,
    )

    assert targeted.route_nodes[1].allowed_vehicle_indices == [1]


def test_forced_residual_insertion_problem_locks_served_shipments_to_seed_truck(sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    trucks = [
        payload.available_trucks[0].model_copy(update={"truck_id": "TRK001", "shift_end": "18:00"}),
        payload.available_trucks[1].model_copy(update={"truck_id": "TRK002", "shift_end": "18:00"}),
    ]
    shipments = [
        RouteNode(
            node_index=1,
            node_kind="shipment",
            order_id="ORD-SERVED",
            parent_order_id="ORD-SERVED",
            spbu_id="SPBU001",
            product_type="PERTALITE",
            demand_kl=8,
            service_time_minutes=30,
            time_window_start=0,
            time_window_end=1439,
            allowed_vehicle_indices=[0, 1],
            matrix_node_name="SPBU001",
        ),
        RouteNode(
            node_index=2,
            node_kind="shipment",
            order_id="ORD-UNSERVED",
            parent_order_id="ORD-UNSERVED",
            spbu_id="SPBU002",
            product_type="PERTALITE",
            demand_kl=8,
            service_time_minutes=30,
            time_window_start=0,
            time_window_end=1439,
            allowed_vehicle_indices=[0, 1],
            matrix_node_name="SPBU002",
        ),
    ]
    problem = PreprocessedProblem(
        depot_id="DPT001",
        depot_name="Depot",
        depot_gate_limit=2,
        depot_operation_window_start=0,
        depot_operation_window_end=1439,
        dispatch_date="2026-04-10",
        depot_service_time_minutes=30,
        config=payload.optimization_config,
        notes=[],
        route_nodes=shipments,
        preassigned_unserved=[],
        orders=payload.orders,
        trucks=trucks,
        spbu_map={},
        time_matrix=[[0]],
        distance_matrix=[[0]],
        matrix_positions={"DEPOT": 0},
    )

    class FakeRouting:
        starts = {0: 100, 1: 110}
        ends = {0: 101, 1: 111}

        def Start(self, vehicle_id):
            return self.starts[vehicle_id]

        def End(self, vehicle_id):
            return self.ends[vehicle_id]

        def IsEnd(self, index):
            return index in set(self.ends.values())

        def NextVar(self, index):
            return ("next", index)

    class FakeManager:
        def IndexToNode(self, index):
            return {
                100: 0,
                101: 0,
                110: 0,
                111: 0,
                1: 1,
            }.get(index, 0)

    class FakeTimeDimension:
        def CumulVar(self, index):
            return ("time", index)

    class FakeAssignment:
        def Value(self, value):
            kind, index = value
            if kind == "next":
                return {
                    100: 1,
                    1: 101,
                    110: 111,
                }[index]
            return {
                100: 360,
                101: 480,
                110: 360,
                111: 420,
            }[index]

    built_model = SimpleNamespace(
        routing=FakeRouting(),
        manager=FakeManager(),
        time_dimension=FakeTimeDimension(),
        distance_dimension=None,
        capacity_dimension=None,
        extra_objective_vars=[],
        extra_objective_weights=[],
    )

    forced = OrToolsSolver._build_forced_residual_insertion_problem(
        problem,
        built_model,
        FakeAssignment(),
        max_candidates_per_shipment=1,
    )

    assert forced.route_nodes[0].allowed_vehicle_indices == [0]
    assert forced.route_nodes[1].allowed_vehicle_indices == [1]


def test_manual_residual_routes_append_reload_and_shipment_to_lowest_working_truck(sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    trucks = [
        payload.available_trucks[0].model_copy(update={"truck_id": "TRK001", "shift_end": "18:00"}),
        payload.available_trucks[1].model_copy(update={"truck_id": "TRK002", "shift_end": "18:00"}),
    ]
    shipments = [
        RouteNode(
            node_index=1,
            node_kind="shipment",
            order_id="ORD-SERVED",
            parent_order_id="ORD-SERVED",
            spbu_id="SPBU001",
            product_type="PERTALITE",
            demand_kl=8,
            service_time_minutes=30,
            time_window_start=0,
            time_window_end=1439,
            allowed_vehicle_indices=[0],
            matrix_node_name="SPBU001",
        ),
        RouteNode(
            node_index=2,
            node_kind="shipment",
            order_id="ORD-UNSERVED",
            parent_order_id="ORD-UNSERVED",
            spbu_id="SPBU002",
            product_type="PERTALITE",
            demand_kl=8,
            service_time_minutes=30,
            time_window_start=0,
            time_window_end=1439,
            allowed_vehicle_indices=[0, 1],
            matrix_node_name="SPBU002",
        ),
        RouteNode(
            node_index=3,
            node_kind="reload",
            order_id="DEPOT_RELOAD#1",
            parent_order_id="-",
            spbu_id="DPT001",
            product_type="-",
            demand_kl=0,
            service_time_minutes=30,
            time_window_start=0,
            time_window_end=1439,
            allowed_vehicle_indices=[0, 1],
            matrix_node_name="DEPOT",
        ),
    ]
    problem = PreprocessedProblem(
        depot_id="DPT001",
        depot_name="Depot",
        depot_gate_limit=2,
        depot_operation_window_start=0,
        depot_operation_window_end=1439,
        dispatch_date="2026-04-10",
        depot_service_time_minutes=30,
        config=payload.optimization_config,
        notes=[],
        route_nodes=shipments,
        preassigned_unserved=[],
        orders=payload.orders,
        trucks=trucks,
        spbu_map={},
        time_matrix=[[0]],
        distance_matrix=[[0]],
        matrix_positions={"DEPOT": 0},
    )

    class FakeRouting:
        starts = {0: 100, 1: 110}
        ends = {0: 101, 1: 111}

        def Start(self, vehicle_id):
            return self.starts[vehicle_id]

        def End(self, vehicle_id):
            return self.ends[vehicle_id]

        def IsEnd(self, index):
            return index in set(self.ends.values())

        def NextVar(self, index):
            return ("next", index)

    class FakeManager:
        def IndexToNode(self, index):
            return {
                100: 0,
                101: 0,
                110: 0,
                111: 0,
                1: 1,
            }.get(index, 0)

    class FakeTimeDimension:
        def CumulVar(self, index):
            return ("time", index)

    class FakeAssignment:
        def Value(self, value):
            kind, index = value
            if kind == "next":
                return {
                    100: 1,
                    1: 101,
                    110: 111,
                }[index]
            return {
                100: 360,
                101: 720,
                110: 360,
                111: 420,
            }[index]

    built_model = SimpleNamespace(
        routing=FakeRouting(),
        manager=FakeManager(),
        time_dimension=FakeTimeDimension(),
        distance_dimension=None,
        capacity_dimension=None,
        extra_objective_vars=[],
        extra_objective_weights=[],
    )

    routes = OrToolsSolver._build_manual_residual_routes(
        problem,
        built_model,
        FakeAssignment(),
        max_candidates_per_shipment=2,
    )

    assert routes == [[1], [3, 2]]


def test_best_effort_pipeline_uses_cleanup_seed_for_following_refinement(
    configured_modules,
    sample_payload,
    monkeypatch,
):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver = OrToolsSolver()

    base_assignment = object()
    cleanup_assignment = object()
    base_model = SimpleNamespace(name="base")
    cleanup_model = SimpleNamespace(name="cleanup")
    captured_seed_models = []

    monkeypatch.setattr(OrToolsSolver, "_allocate_best_effort_budgets", staticmethod(lambda _seconds: (10, 0, 5, 5, 5)))
    monkeypatch.setattr(
        OrToolsSolver,
        "_solve_stage",
        lambda self, _problem, **_kwargs: ortools_solver_module.StageSolveResult(
            built_model=base_model,
            assignment=base_assignment,
            search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
        ),
    )
    monkeypatch.setattr(
        OrToolsSolver,
        "_count_unserved_shipments",
        staticmethod(lambda _problem, _model, assignment: 2 if assignment is base_assignment else 0),
    )
    monkeypatch.setattr(
        OrToolsSolver,
        "_run_targeted_cleanup_repair",
        lambda self, _problem, **_kwargs: (cleanup_model, cleanup_assignment, 0),
    )

    def fake_refine(self, _problem, *, seed_model, seed_assignment, **_kwargs):
        captured_seed_models.append((seed_model, seed_assignment))
        return ortools_solver_module.StageSolveResult(
            built_model=seed_model,
            assignment=None,
            search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT,
        )

    monkeypatch.setattr(OrToolsSolver, "_refine_stage", fake_refine)

    output = solver._run_best_effort_pipeline(
        problem,
        started=0.0,
        total_seconds=25,
    )

    assert output.assignment is cleanup_assignment
    assert all(seed_model is cleanup_model for seed_model, _seed_assignment in captured_seed_models)
    assert "targeted cleanup repair" in output.message


def test_best_effort_pipeline_uses_forced_residual_seed_when_cleanup_does_not_improve(
    configured_modules,
    sample_payload,
    monkeypatch,
):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver = OrToolsSolver()

    base_assignment = object()
    forced_assignment = object()
    base_model = SimpleNamespace(name="base")
    forced_model = SimpleNamespace(name="forced")
    captured_seed_models = []

    monkeypatch.setattr(OrToolsSolver, "_allocate_best_effort_budgets", staticmethod(lambda _seconds: (10, 0, 6, 5, 5)))
    monkeypatch.setattr(
        OrToolsSolver,
        "_solve_stage",
        lambda self, _problem, **_kwargs: ortools_solver_module.StageSolveResult(
            built_model=base_model,
            assignment=base_assignment,
            search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
        ),
    )
    monkeypatch.setattr(
        OrToolsSolver,
        "_count_unserved_shipments",
        staticmethod(lambda _problem, _model, assignment: 2 if assignment is base_assignment else 0),
    )
    monkeypatch.setattr(OrToolsSolver, "_run_targeted_cleanup_repair", lambda self, _problem, **_kwargs: None)
    monkeypatch.setattr(
        OrToolsSolver,
        "_run_forced_residual_insertion",
        lambda self, _problem, **_kwargs: (forced_model, forced_assignment, 0),
    )

    def fake_refine(self, _problem, *, seed_model, seed_assignment, **_kwargs):
        captured_seed_models.append((seed_model, seed_assignment))
        return ortools_solver_module.StageSolveResult(
            built_model=seed_model,
            assignment=None,
            search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT,
        )

    monkeypatch.setattr(OrToolsSolver, "_refine_stage", fake_refine)

    output = solver._run_best_effort_pipeline(
        problem,
        started=0.0,
        total_seconds=26,
    )

    assert output.assignment is forced_assignment
    assert all(seed_model is forced_model for seed_model, _seed_assignment in captured_seed_models)
    assert "forced residual insertion" in output.message


def test_forced_residual_insertion_uses_manual_seed_when_local_attempts_fail(
    configured_modules,
    sample_payload,
    monkeypatch,
):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver = OrToolsSolver()

    seed_model = SimpleNamespace(name="seed")
    seed_assignment = object()
    manual_assignment = object()
    manual_model = SimpleNamespace(name="manual")

    monkeypatch.setattr(OrToolsSolver, "_targeted_cleanup_candidate_limits", staticmethod(lambda _problem, _unserved: [1]))
    monkeypatch.setattr(OrToolsSolver, "_allocate_cleanup_attempt_budgets", staticmethod(lambda _seconds, _attempts: [1, 1]))
    monkeypatch.setattr(OrToolsSolver, "_build_forced_residual_insertion_problem", staticmethod(lambda problem, *_args, **_kwargs: problem))
    monkeypatch.setattr(
        OrToolsSolver,
        "_refine_stage",
        lambda self, _problem, **_kwargs: ortools_solver_module.StageSolveResult(
            built_model=seed_model,
            assignment=None,
            search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT,
        ),
    )
    monkeypatch.setattr(OrToolsSolver, "_build_manual_residual_routes", staticmethod(lambda *_args, **_kwargs: [[1], [2]]))
    monkeypatch.setattr(
        OrToolsSolver,
        "_solve_from_manual_routes",
        staticmethod(
            lambda _problem, _routes, **_kwargs: ortools_solver_module.StageSolveResult(
                built_model=manual_model,
                assignment=manual_assignment,
                search_status=routing_enums_pb2.RoutingSearchStatus.ROUTING_SUCCESS,
            )
        ),
    )
    monkeypatch.setattr(
        OrToolsSolver,
        "_count_unserved_shipments",
        staticmethod(lambda _problem, _model, assignment: 0 if assignment is manual_assignment else 2),
    )

    result = solver._run_forced_residual_insertion(
        problem,
        seed_model=seed_model,
        seed_assignment=seed_assignment,
        current_unserved=2,
        time_limit_seconds=2,
    )

    assert result is not None
    model, assignment, unserved = result
    assert model is manual_model
    assert assignment is manual_assignment
    assert unserved == 0


def test_solver_respects_depot_gate_limit_queue(configured_modules, monkeypatch):
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "gate_limit", 1)
    monkeypatch.setattr(
        master_data_module,
        "MOCK_SPBU",
        [
            {
                "spbu_id": "SPBU001",
                "name": "SPBU A",
                "lat": -6.11,
                "lng": 106.71,
                "time_window_start": "08:00",
                "time_window_end": "08:20",
                "allowed_truck_types": ["SMALL"],
            },
            {
                "spbu_id": "SPBU002",
                "name": "SPBU B",
                "lat": -6.12,
                "lng": 106.72,
                "time_window_start": "08:00",
                "time_window_end": "08:20",
                "allowed_truck_types": ["SMALL"],
            },
        ],
    )
    payload = schemas.OptimizationRequest.model_validate(
        {
            "dispatch_date": "2026-02-10",
            "depot_id": "DPT001",
            "depot_service_time_minutes": 20,
            "orders": [
                {
                    "order_id": "ORD001",
                    "spbu_id": "SPBU001",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 10,
                    "time_window_start": "08:00",
                    "time_window_end": "08:20",
                },
                {
                    "order_id": "ORD002",
                    "spbu_id": "SPBU002",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 10,
                    "time_window_start": "08:00",
                    "time_window_end": "08:20",
                },
            ],
            "available_trucks": [
                    {
                        "truck_id": "TRK001",
                        "truck_type": "SMALL",
                        "truck_category": 2,
                        "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                },
                    {
                        "truck_id": "TRK002",
                        "truck_type": "SMALL",
                        "truck_category": 2,
                        "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                },
            ],
                "optimization_config": {
                    "minimize_truck_count": True,
                    "minimize_distance": True,
                    "minimize_time": True,
                    "minimize_depot_operation_time": False,
                    "hard_constraints": {
                        "capacity_limit": True,
                        "time_window": True,
                    "compatibility": True,
                    "depot_operation_window": True,
                    "max_route_duration": False,
                    "max_vehicle_working_time": True,
                    "max_total_distance_per_vehicle": False,
                },
                "soft_constraints": {
                    "allow_unserved_orders": False,
                    "allow_overtime": True,
                    "depot_operation_window": False,
                },
                "penalties": {
                    "unserved_order_penalty": 100000,
                    "late_arrival_penalty_per_minute": 100,
                    "overtime_penalty_per_minute": 50,
                    "depot_operation_window_penalty_per_minute": 50,
                    "capacity_violation_penalty": 0,
                    "activation_cost_vehicle": 10000,
                    "distance_weight": 1,
                    "time_weight": 1,
                },
                "solver_options": {
                    "max_solver_seconds": 5,
                    "first_solution_strategy": "PATH_CHEAPEST_ARC",
                    "local_search_metaheuristic": "GUIDED_LOCAL_SEARCH",
                },
                "max_route_duration_minutes": None,
                "max_vehicle_working_time_minutes": 720,
                "max_total_distance_per_vehicle_km": None,
                "max_lateness_minutes": 0,
            },
        }
    )

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000004",
        problem,
        OrToolsSolver().solve(problem),
    )

    start_times = sorted(
        hhmm_to_minutes(route.origin_service_start)
        for route in result.route_details
        if route.origin_service_start
    )

    assert len(start_times) >= 2
    assert start_times[1] - start_times[0] >= 20


def test_solver_uses_all_available_depot_gates_for_active_trucks(configured_modules, monkeypatch):
    monkeypatch.setattr(
        master_data_module,
        "MOCK_SPBU",
        [
                {
                    "spbu_id": f"SPBU00{index}",
                    "name": f"SPBU {index}",
                    "lat": -6.2 - (index * 0.01),
                    "lng": 106.8 + (index * 0.01),
                    "time_window_start": "08:00",
                    "time_window_end": "08:15",
                    "truck_category": 4,
                    "allowed_truck_types": ["SMALL"],
                }
                for index in range(1, 6)
            ],
        )
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "gate_limit", 4)

    payload = schemas.OptimizationRequest.model_validate(
        {
            "dispatch_date": "2026-02-10",
            "depot_id": "DPT001",
            "depot_service_time_minutes": 20,
            "orders": [
                {
                    "order_id": f"ORD00{index}",
                    "spbu_id": f"SPBU00{index}",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 10,
                    "time_window_start": "08:00",
                    "time_window_end": "08:15",
                }
                for index in range(1, 6)
            ],
            "available_trucks": [
                    {
                        "truck_id": "TRK001",
                        "truck_type": "SMALL",
                        "truck_category": 2,
                        "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                },
                    {
                        "truck_id": "TRK002",
                        "truck_type": "SMALL",
                        "truck_category": 2,
                        "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                },
                    {
                        "truck_id": "TRK003",
                        "truck_type": "SMALL",
                        "truck_category": 2,
                        "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTAMAX"],
                },
                    {
                        "truck_id": "TRK004",
                        "truck_type": "SMALL",
                        "truck_category": 2,
                        "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                },
                    {
                        "truck_id": "TRK005",
                        "truck_type": "SMALL",
                        "truck_category": 2,
                        "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                },
                    {
                        "truck_id": "TRK006",
                        "truck_type": "SMALL",
                        "truck_category": 2,
                        "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                },
            ],
            "optimization_config": {
                "minimize_truck_count": True,
                "minimize_distance": True,
                "minimize_time": True,
                "minimize_depot_operation_time": False,
                "hard_constraints": {
                    "capacity_limit": True,
                    "time_window": True,
                    "compatibility": True,
                    "depot_operation_window": True,
                    "max_route_duration": False,
                    "max_vehicle_working_time": True,
                    "max_total_distance_per_vehicle": False,
                },
                "soft_constraints": {
                    "allow_unserved_orders": False,
                    "allow_overtime": True,
                    "depot_operation_window": False,
                },
                "penalties": {
                    "unserved_order_penalty": 100000,
                    "late_arrival_penalty_per_minute": 100,
                    "overtime_penalty_per_minute": 50,
                    "depot_operation_window_penalty_per_minute": 50,
                    "capacity_violation_penalty": 0,
                    "activation_cost_vehicle": 10000,
                    "distance_weight": 1,
                    "time_weight": 1,
                },
                "solver_options": {
                    "max_solver_seconds": 5,
                    "first_solution_strategy": "PATH_CHEAPEST_ARC",
                    "local_search_metaheuristic": "GUIDED_LOCAL_SEARCH",
                },
                "max_route_duration_minutes": None,
                "max_vehicle_working_time_minutes": 720,
                "max_total_distance_per_vehicle_km": None,
                "max_lateness_minutes": 0,
            },
        }
    )

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000005",
        problem,
        OrToolsSolver().solve(problem),
    )

    start_times = sorted(
        hhmm_to_minutes(route.origin_service_start)
        for route in result.route_details
        if route.origin_service_start
    )

    assert len(start_times) == 5
    assert start_times.count(start_times[0]) == 4
    assert start_times[4] - start_times[0] >= 20


def test_solver_supports_multi_trip_with_depot_reload(configured_modules, monkeypatch):
    monkeypatch.setattr(
        master_data_module,
        "MOCK_SPBU",
        [
            {
                "spbu_id": "SPBU001",
                "name": "SPBU A",
                "lat": -6.11,
                "lng": 106.71,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
            {
                "spbu_id": "SPBU002",
                "name": "SPBU B",
                "lat": -6.12,
                "lng": 106.72,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
            {
                "spbu_id": "SPBU003",
                "name": "SPBU C",
                "lat": -6.13,
                "lng": 106.73,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
        ],
    )
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "gate_limit", 2)

    payload = schemas.OptimizationRequest.model_validate(
        {
            "dispatch_date": "2026-02-10",
            "depot_id": "DPT001",
            "depot_service_time_minutes": 15,
            "orders": [
                {
                    "order_id": "ORD001",
                    "spbu_id": "SPBU001",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 20,
                    "time_window_start": "08:00",
                    "time_window_end": "17:00",
                },
                {
                    "order_id": "ORD002",
                    "spbu_id": "SPBU002",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 20,
                    "time_window_start": "08:00",
                    "time_window_end": "17:00",
                },
                {
                    "order_id": "ORD003",
                    "spbu_id": "SPBU003",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 20,
                    "time_window_start": "08:00",
                    "time_window_end": "17:00",
                },
            ],
            "available_trucks": [
                {
                    "truck_id": "TRK001",
                    "truck_type": "SMALL",
                    "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                }
            ],
            "optimization_config": {
                "minimize_truck_count": True,
                "minimize_distance": True,
                "minimize_time": True,
                "hard_constraints": {
                    "capacity_limit": True,
                    "time_window": True,
                    "compatibility": True,
                    "depot_operation_window": True,
                    "max_route_duration": True,
                    "max_vehicle_working_time": True,
                    "max_total_distance_per_vehicle": True,
                },
                "soft_constraints": {
                    "allow_unserved_orders": False,
                    "allow_overtime": True,
                    "depot_operation_window": False,
                },
                "penalties": {
                    "unserved_order_penalty": 100000,
                    "late_arrival_penalty_per_minute": 100,
                    "overtime_penalty_per_minute": 50,
                    "depot_operation_window_penalty_per_minute": 50,
                    "capacity_violation_penalty": 0,
                    "activation_cost_vehicle": 10000,
                    "distance_weight": 1,
                    "time_weight": 1,
                },
                "solver_options": {
                    "max_solver_seconds": 5,
                    "first_solution_strategy": "PATH_CHEAPEST_ARC",
                    "local_search_metaheuristic": "GUIDED_LOCAL_SEARCH",
                },
                "max_route_duration_minutes": 480,
                "max_vehicle_working_time_minutes": 480,
                "max_total_distance_per_vehicle_km": 200,
                "max_lateness_minutes": 120,
            },
        }
    )

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000006",
        problem,
        OrToolsSolver().solve(problem),
    )

    assert result.status == "feasible"
    assert result.active_truck_count == 1
    assert result.total_delivered_demand == 24
    assert len(result.route_details) == 1
    route = result.route_details[0]
    assert route.trip_count == 3
    assert len([stop for stop in route.stops if stop.stop_kind == "depot_reload"]) == 2
    assert [stop.stop_kind for stop in route.stops].count("delivery") == 3


def test_trucks_are_normalized_compatible_with_all_supported_products(configured_modules, sample_payload):
    sample_payload["orders"] = [
        {
            "order_id": "ORD001",
            "spbu_id": "SPBU001",
            "product_type": "PERTAMAX_TURBO",
            "demand_kl": 8,
            "service_time_minutes": 30,
            "time_window_start": "08:00",
            "time_window_end": "15:00",
        }
    ]
    sample_payload["available_trucks"] = [
        {
            "truck_id": "TRK001",
            "truck_type": "SMALL",
            "truck_category": 2,
            "capacity_kl": 8,
            "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
            "fixed_cost": 1000,
            "variable_cost_per_km": 10,
            "variable_cost_per_minute": 2,
            "start_depot_id": "DPT001",
            "end_depot_id": "DPT001",
            "shift_start": "06:00",
            "shift_end": "18:00",
            "compatible_product_types": ["PERTALITE"],
        }
    ]

    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)

    assert problem.preassigned_unserved == []
    assert problem.shipments[0].product_type == "PERTAMAX_TURBO"
    assert payload.available_trucks[0].compatible_product_types == schemas.SUPPORTED_PRODUCT_TYPES


def test_single_compartment_truck_must_reload_before_second_shipment(configured_modules, sample_payload):
    sample_payload["orders"] = [
        {
            "order_id": "ORD001",
            "spbu_id": "SPBU001",
            "product_type": "PERTALITE",
            "demand_kl": 4,
            "service_time_minutes": 30,
            "time_window_start": "08:00",
            "time_window_end": "17:00",
        },
        {
            "order_id": "ORD002",
            "spbu_id": "SPBU002",
            "product_type": "PERTAMAX",
            "demand_kl": 4,
            "service_time_minutes": 25,
            "time_window_start": "09:00",
            "time_window_end": "17:00",
        },
    ]
    sample_payload["available_trucks"] = [
        {
            "truck_id": "TRK001",
            "truck_type": "SMALL",
            "truck_category": 2,
            "capacity_kl": 8,
            "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
            "fixed_cost": 1000,
            "variable_cost_per_km": 10,
            "variable_cost_per_minute": 2,
            "start_depot_id": "DPT001",
            "end_depot_id": "DPT001",
            "shift_start": "06:00",
            "shift_end": "18:00",
            "compatible_product_types": ["PERTALITE"],
        }
    ]

    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000016",
        problem,
        OrToolsSolver().solve(problem),
    )

    assert result.status == "feasible"
    assert len(result.route_details) == 1
    assert [stop.stop_kind for stop in result.route_details[0].stops] == [
        "delivery",
        "depot_reload",
        "delivery",
    ]


def test_solver_respects_max_vehicle_working_time_on_multi_trip(configured_modules, monkeypatch):
    monkeypatch.setattr(
        master_data_module,
        "MOCK_SPBU",
        [
            {
                "spbu_id": "SPBU001",
                "name": "SPBU A",
                "lat": -6.11,
                "lng": 106.71,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
            {
                "spbu_id": "SPBU002",
                "name": "SPBU B",
                "lat": -6.12,
                "lng": 106.72,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
            {
                "spbu_id": "SPBU003",
                "name": "SPBU C",
                "lat": -6.13,
                "lng": 106.73,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
        ],
    )

    payload = schemas.OptimizationRequest.model_validate(
        {
            "dispatch_date": "2026-02-10",
            "depot_id": "DPT001",
            "depot_service_time_minutes": 20,
            "orders": [
                {
                    "order_id": "ORD001",
                    "spbu_id": "SPBU001",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 25,
                    "time_window_start": "08:00",
                    "time_window_end": "17:00",
                },
                {
                    "order_id": "ORD002",
                    "spbu_id": "SPBU002",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 25,
                    "time_window_start": "08:00",
                    "time_window_end": "17:00",
                },
                {
                    "order_id": "ORD003",
                    "spbu_id": "SPBU003",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 25,
                    "time_window_start": "08:00",
                    "time_window_end": "17:00",
                },
            ],
            "available_trucks": [
                {
                    "truck_id": "TRK001",
                    "truck_type": "SMALL",
                    "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                }
            ],
            "optimization_config": {
                "minimize_truck_count": True,
                "minimize_distance": True,
                "minimize_time": True,
                "hard_constraints": {
                    "capacity_limit": True,
                    "time_window": True,
                    "compatibility": True,
                    "depot_operation_window": True,
                    "max_route_duration": False,
                    "max_vehicle_working_time": True,
                    "max_total_distance_per_vehicle": False,
                },
                "soft_constraints": {
                    "allow_unserved_orders": False,
                    "allow_overtime": True,
                    "depot_operation_window": False,
                },
                "penalties": {
                    "unserved_order_penalty": 100000,
                    "late_arrival_penalty_per_minute": 100,
                    "overtime_penalty_per_minute": 50,
                    "depot_operation_window_penalty_per_minute": 50,
                    "capacity_violation_penalty": 0,
                    "activation_cost_vehicle": 10000,
                    "distance_weight": 1,
                    "time_weight": 1,
                },
                "solver_options": {
                    "max_solver_seconds": 5,
                    "first_solution_strategy": "PATH_CHEAPEST_ARC",
                    "local_search_metaheuristic": "GUIDED_LOCAL_SEARCH",
                },
                "max_route_duration_minutes": None,
                "max_vehicle_working_time_minutes": 90,
                "max_total_distance_per_vehicle_km": None,
                "max_lateness_minutes": 120,
            },
        }
    )

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = OrToolsSolver().solve(problem)

    assert solver_output.assignment is None


def test_solver_hard_depot_operation_window_can_make_multi_trip_infeasible(configured_modules, monkeypatch):
    monkeypatch.setattr(
        master_data_module,
        "MOCK_SPBU",
        [
            {
                "spbu_id": "SPBU001",
                "name": "SPBU A",
                "lat": -6.11,
                "lng": 106.71,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
            {
                "spbu_id": "SPBU002",
                "name": "SPBU B",
                "lat": -6.12,
                "lng": 106.72,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
        ],
    )
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "gate_limit", 1)
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "time_window_start", "06:00")
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "time_window_end", "07:00")

    payload = schemas.OptimizationRequest.model_validate(
        {
            "dispatch_date": "2026-02-10",
            "depot_id": "DPT001",
            "depot_service_time_minutes": 30,
            "orders": [
                {
                    "order_id": "ORD001",
                    "spbu_id": "SPBU001",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 20,
                    "time_window_start": "08:00",
                    "time_window_end": "17:00",
                },
                {
                    "order_id": "ORD002",
                    "spbu_id": "SPBU002",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 20,
                    "time_window_start": "08:00",
                    "time_window_end": "17:00",
                },
            ],
            "available_trucks": [
                {
                    "truck_id": "TRK001",
                    "truck_type": "SMALL",
                    "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 0,
                    "variable_cost_per_km": 0,
                    "variable_cost_per_minute": 0,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                },
            ],
            "optimization_config": {
                "minimize_truck_count": False,
                "minimize_distance": False,
                "minimize_time": False,
                "hard_constraints": {
                    "capacity_limit": True,
                    "time_window": True,
                    "compatibility": True,
                    "depot_operation_window": True,
                    "max_route_duration": False,
                    "max_vehicle_working_time": True,
                    "max_total_distance_per_vehicle": False,
                },
                "soft_constraints": {
                    "allow_unserved_orders": False,
                    "allow_overtime": True,
                    "depot_operation_window": False,
                },
                "penalties": {
                    "unserved_order_penalty": 100000,
                    "late_arrival_penalty_per_minute": 100,
                    "overtime_penalty_per_minute": 50,
                    "depot_operation_window_penalty_per_minute": 25,
                    "capacity_violation_penalty": 0,
                    "activation_cost_vehicle": 0,
                    "distance_weight": 0,
                    "time_weight": 0,
                },
                "solver_options": {
                    "max_solver_seconds": 5,
                    "first_solution_strategy": "PATH_CHEAPEST_ARC",
                    "local_search_metaheuristic": "GUIDED_LOCAL_SEARCH",
                },
                "max_route_duration_minutes": None,
                "max_vehicle_working_time_minutes": 720,
                "max_total_distance_per_vehicle_km": None,
                "max_lateness_minutes": 120,
            },
        }
    )

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = OrToolsSolver().solve(problem)

    assert solver_output.assignment is None


def test_solver_soft_depot_operation_window_adds_penalty(configured_modules, monkeypatch):
    monkeypatch.setattr(
        master_data_module,
        "MOCK_SPBU",
        [
            {
                "spbu_id": "SPBU001",
                "name": "SPBU A",
                "lat": -6.11,
                "lng": 106.71,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
            {
                "spbu_id": "SPBU002",
                "name": "SPBU B",
                "lat": -6.12,
                "lng": 106.72,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "allowed_truck_types": ["SMALL"],
            },
        ],
    )
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "gate_limit", 1)
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "time_window_start", "06:00")
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "time_window_end", "06:10")

    payload = schemas.OptimizationRequest.model_validate(
        {
            "dispatch_date": "2026-02-10",
            "depot_id": "DPT001",
            "depot_service_time_minutes": 30,
            "orders": [
                {
                    "order_id": "ORD001",
                    "spbu_id": "SPBU001",
                    "product_type": "PERTALITE",
                    "demand_kl": 8,
                    "service_time_minutes": 20,
                    "time_window_start": "08:00",
                    "time_window_end": "17:00",
                },
            ],
            "available_trucks": [
                {
                    "truck_id": "TRK001",
                    "truck_type": "SMALL",
                    "capacity_kl": 8,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 8}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "18:00",
                    "compatible_product_types": ["PERTALITE"],
                }
            ],
            "optimization_config": {
                "minimize_truck_count": False,
                "minimize_distance": False,
                "minimize_time": False,
                "hard_constraints": {
                    "capacity_limit": True,
                    "time_window": True,
                    "compatibility": True,
                    "depot_operation_window": False,
                    "max_route_duration": False,
                    "max_vehicle_working_time": True,
                    "max_total_distance_per_vehicle": False,
                },
                "soft_constraints": {
                    "allow_unserved_orders": False,
                    "allow_overtime": True,
                    "depot_operation_window": True,
                },
                "penalties": {
                    "unserved_order_penalty": 100000,
                    "late_arrival_penalty_per_minute": 100,
                    "overtime_penalty_per_minute": 50,
                    "depot_operation_window_penalty_per_minute": 25,
                    "capacity_violation_penalty": 0,
                    "activation_cost_vehicle": 10000,
                    "distance_weight": 0,
                    "time_weight": 0,
                },
                "solver_options": {
                    "max_solver_seconds": 5,
                    "first_solution_strategy": "PATH_CHEAPEST_ARC",
                    "local_search_metaheuristic": "GUIDED_LOCAL_SEARCH",
                },
                "max_route_duration_minutes": None,
                "max_vehicle_working_time_minutes": 720,
                "max_total_distance_per_vehicle_km": None,
                "max_lateness_minutes": 120,
            },
        }
    )

    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    solver_output = OrToolsSolver().solve(problem)
    result = ResultService().build_response(
        "00000000-0000-0000-0000-000000000008",
        problem,
        solver_output,
    )

    assert solver_output.assignment is not None
    assert result.status == "feasible"
    assert result.total_penalty > 0
    assert result.total_cost >= result.total_penalty


def test_result_service_collapses_initial_depot_reload_block_into_wait():
    service = ResultService()
    raw_stops = [
        schemas.RouteStopResponse(
            sequence=1,
            order_id="DEPOT_RELOAD#1",
            parent_order_id="-",
            spbu_id="DPT001",
            stop_kind="depot_reload",
            trip_sequence=2,
            spbu_name="Depot Test",
            travel_path="",
            segment_max_velocity_kmh="-",
            travel_distance_km=0,
            travel_time_minutes=0,
            eta="06:30",
            etd="07:00",
            delivered_volume=0,
            arrival_status="reloaded_at_depot",
        ),
        schemas.RouteStopResponse(
            sequence=2,
            order_id="DEPOT_RELOAD#2",
            parent_order_id="-",
            spbu_id="DPT001",
            stop_kind="depot_reload",
            trip_sequence=3,
            spbu_name="Depot Test",
            travel_path="",
            segment_max_velocity_kmh="-",
            travel_distance_km=0,
            travel_time_minutes=0,
            eta="07:00",
            etd="07:30",
            delivered_volume=0,
            arrival_status="reloaded_at_depot",
        ),
        schemas.RouteStopResponse(
            sequence=3,
            order_id="ORD001",
            parent_order_id="ORD001",
            spbu_id="SPBU001",
            stop_kind="delivery",
            trip_sequence=3,
            spbu_name="SPBU A",
            travel_path="DPT001 -> SPBU001",
            segment_max_velocity_kmh="40",
            travel_distance_km=10,
            travel_time_minutes=30,
            eta="08:00",
            etd="08:30",
            delivered_volume=8,
            arrival_status="on_time",
        ),
    ]

    normalized, trip_count = service._normalize_route_stops(raw_stops)

    assert [stop.stop_kind for stop in normalized] == ["depot_wait", "delivery"]
    assert normalized[0].order_id == "DEPOT_WAIT#1"
    assert normalized[0].eta == "06:30"
    assert normalized[0].etd == "07:30"
    assert normalized[0].arrival_status == "waiting_at_depot"
    assert normalized[0].trip_sequence == 1
    assert normalized[1].trip_sequence == 1
    assert trip_count == 1


def test_result_service_preserves_reload_before_wait_when_delivery_follows():
    service = ResultService()
    raw_stops = [
        schemas.RouteStopResponse(
            sequence=1,
            order_id="ORD001",
            parent_order_id="ORD001",
            spbu_id="SPBU001",
            stop_kind="delivery",
            trip_sequence=1,
            spbu_name="SPBU A",
            travel_path="DPT001 -> SPBU001",
            segment_max_velocity_kmh="40",
            travel_distance_km=10,
            travel_time_minutes=30,
            eta="08:00",
            etd="08:30",
            delivered_volume=8,
            arrival_status="on_time",
        ),
        schemas.RouteStopResponse(
            sequence=2,
            order_id="DEPOT_RELOAD#1",
            parent_order_id="-",
            spbu_id="DPT001",
            stop_kind="depot_reload",
            trip_sequence=2,
            spbu_name="Depot Test",
            travel_path="SPBU001 -> DPT001",
            segment_max_velocity_kmh="-",
            travel_distance_km=10,
            travel_time_minutes=30,
            eta="09:00",
            etd="09:30",
            delivered_volume=0,
            arrival_status="reloaded_at_depot",
        ),
        schemas.RouteStopResponse(
            sequence=3,
            order_id="DEPOT_WAIT#1",
            parent_order_id="-",
            spbu_id="DPT001",
            stop_kind="depot_wait",
            trip_sequence=2,
            spbu_name="Depot Test",
            travel_path="",
            segment_max_velocity_kmh="-",
            travel_distance_km=None,
            travel_time_minutes=None,
            eta="09:30",
            etd="10:00",
            delivered_volume=0,
            arrival_status="waiting_at_depot",
        ),
        schemas.RouteStopResponse(
            sequence=4,
            order_id="ORD002",
            parent_order_id="ORD002",
            spbu_id="SPBU002",
            stop_kind="delivery",
            trip_sequence=2,
            spbu_name="SPBU B",
            travel_path="DPT001 -> SPBU002",
            segment_max_velocity_kmh="40",
            travel_distance_km=12,
            travel_time_minutes=35,
            eta="11:00",
            etd="11:30",
            delivered_volume=8,
            arrival_status="on_time",
        ),
    ]

    normalized, trip_count = service._normalize_route_stops(raw_stops)

    assert [stop.stop_kind for stop in normalized] == ["delivery", "depot_reload", "depot_wait", "delivery"]
    assert normalized[1].order_id == "DEPOT_RELOAD#1"
    assert normalized[1].trip_sequence == 2
    assert normalized[2].order_id == "DEPOT_WAIT#1"
    assert normalized[2].trip_sequence == 2
    assert normalized[3].trip_sequence == 2
    assert trip_count == 2


def test_persisted_leg_snapshot_handles_next_day_return_time():
    service = ResultService()

    snapshot = service._build_persisted_leg_snapshot(
        "94",
        "65",
        origin_etd="18:00",
        destination_eta="00:00",
    )

    assert snapshot["travel_path"] == "94 -> 65"
    assert snapshot["travel_time_minutes"] == 360.0


def test_persisted_leg_snapshot_uses_network_audit_for_path_and_max_velocity():
    service = ResultService(
        network_client=SimpleNamespace(
            get_leg_audit=lambda origin_id, destination_id: {
                "travel_path": f"{origin_id} -> HUB01 -> {destination_id}",
                "segment_max_velocity_kmh": "35 / 25",
                "travel_distance_km": 42.5,
                "travel_time_minutes": 999.0,
            }
        )
    )

    snapshot = service._build_persisted_leg_snapshot(
        "65",
        "74",
        origin_etd="06:30",
        destination_eta="08:00",
    )

    assert snapshot["travel_path"] == "65 -> HUB01 -> 74"
    assert snapshot["segment_max_velocity_kmh"] == "35 / 25"
    assert snapshot["travel_distance_km"] == 42.5
    assert snapshot["travel_time_minutes"] == 90.0


def test_depot_operation_end_uses_last_gate_out_not_return_eta():
    service = ResultService()
    routes = [
        schemas.RouteDetailResponse(
            truck_id="TRK001",
            origin_name="Depot Test",
            origin_service_start="06:00",
            origin_etd="06:30",
            return_eta="19:00",
            truck_type="SMALL",
            capacity_kl=8,
            total_load=8,
            utilization_percent=100,
            route_distance=10,
            route_time=780,
            stop_count=1,
            stops=[
                schemas.RouteStopResponse(
                    sequence=1,
                    order_id="ORD001",
                    parent_order_id="ORD001",
                    spbu_id="SPBU001",
                    stop_kind="delivery",
                    spbu_name="SPBU A",
                    eta="08:00",
                    etd="08:30",
                    delivered_volume=8,
                    arrival_status="on_time",
                )
            ],
        ),
        schemas.RouteDetailResponse(
            truck_id="TRK002",
            origin_name="Depot Test",
            origin_service_start="07:00",
            origin_etd="07:30",
            return_eta="21:00",
            truck_type="SMALL",
            capacity_kl=8,
            total_load=8,
            utilization_percent=100,
            route_distance=10,
            route_time=840,
            stop_count=2,
            stops=[
                schemas.RouteStopResponse(
                    sequence=1,
                    order_id="DEPOT_RELOAD#1",
                    parent_order_id="-",
                    spbu_id="DPT001",
                    stop_kind="depot_reload",
                    spbu_name="Depot Test",
                    eta="13:00",
                    etd="13:30",
                    delivered_volume=0,
                    arrival_status="reloaded_at_depot",
                ),
                schemas.RouteStopResponse(
                    sequence=2,
                    order_id="ORD002",
                    parent_order_id="ORD002",
                    spbu_id="SPBU002",
                    stop_kind="delivery",
                    spbu_name="SPBU B",
                    eta="15:00",
                    etd="15:30",
                    delivered_volume=8,
                    arrival_status="on_time",
                ),
            ],
        ),
    ]

    total_minutes, operation_start, operation_end = service._calculate_depot_operation_window(routes)

    assert operation_start == "06:00"
    assert operation_end == "13:30"
    assert total_minutes == 450
