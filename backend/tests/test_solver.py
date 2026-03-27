"""Tests for solver behavior."""

from __future__ import annotations

from app.models import schemas
from app.services import master_data_client as master_data_module
from app.services.preprocessing_service import PreprocessingService
from app.services.result_service import ResultService
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


def test_solver_adds_depot_service_time_per_truck(configured_modules, sample_payload):
    base_payload = schemas.OptimizationRequest.model_validate(sample_payload)
    base_payload.orders = [base_payload.orders[0].model_copy(update={"demand_kl": 8})]
    base_payload.available_trucks = [base_payload.available_trucks[0]]
    base_payload.depot_service_time_minutes = 0

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
                    "fixed_cost_vehicle": 10000,
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
                    "fixed_cost_vehicle": 10000,
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
                    "fixed_cost_vehicle": 10000,
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
                    "fixed_cost_vehicle": 10000,
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
                    "fixed_cost_vehicle": 0,
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
                    "fixed_cost_vehicle": 10000,
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
