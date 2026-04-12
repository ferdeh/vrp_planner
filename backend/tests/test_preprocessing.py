"""Tests for preprocessing service."""

from __future__ import annotations

import pytest

from app.models import schemas
from app.services import master_data_client as master_data_module
from app.services.preprocessing_service import PreprocessingService
from app.services.network_client import NetworkDataError


def test_preprocessing_splits_large_order(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    payload.orders[0].demand_kl = 20
    service = PreprocessingService()

    problem = service.preprocess(payload, payload.optimization_config)

    assert len(problem.shipments) == 4
    assert len([shipment for shipment in problem.shipments if shipment.parent_order_id == "ORD001"]) == 3
    assert [shipment.demand_kl for shipment in problem.shipments if shipment.parent_order_id == "ORD001"] == [8, 8, 4]
    assert any(note.code == "ORDER_SPLIT" for note in problem.notes)


def test_preprocessing_marks_spbu_category_incompatible_order_unserved(configured_modules, sample_payload, monkeypatch):
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
                "truck_category": 1,
                "allowed_truck_types": ["LARGE"],
            },
            {
                "spbu_id": "SPBU002",
                "name": "SPBU B",
                "lat": -6.12,
                "lng": 106.72,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "truck_category": 4,
                "allowed_truck_types": ["SMALL", "MEDIUM", "LARGE"],
            },
        ],
    )
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    service = PreprocessingService()

    problem = service.preprocess(payload, payload.optimization_config)

    assert len(problem.preassigned_unserved) == 1
    assert problem.preassigned_unserved[0].order_id == "ORD001"
    assert problem.preassigned_unserved[0].reason == "No truck matches SPBU truck category policy."


def test_preprocessing_respects_spbu_truck_category_limit(configured_modules, sample_payload, monkeypatch):
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
                "truck_category": 4,
                "allowed_truck_types": ["SMALL", "MEDIUM", "LARGE"],
            },
            {
                "spbu_id": "SPBU002",
                "name": "SPBU B",
                "lat": -6.12,
                "lng": 106.72,
                "time_window_start": "08:00",
                "time_window_end": "17:00",
                "truck_category": 4,
                "allowed_truck_types": ["SMALL", "MEDIUM", "LARGE"],
            },
        ],
    )
    sample_payload["available_trucks"][0]["truck_category"] = 5
    sample_payload["available_trucks"][1]["truck_category"] = 3
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    service = PreprocessingService()

    problem = service.preprocess(payload, payload.optimization_config)

    shipment = next(item for item in problem.shipments if item.parent_order_id == "ORD001")
    assert shipment.allowed_vehicle_indices == [1]


def test_preprocessing_no_split_uses_max_compartment_capacity(configured_modules, sample_payload):
    sample_payload["optimization_config"]["hard_constraints"]["no_split_order"] = True
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    service = PreprocessingService()

    problem = service.preprocess(payload, payload.optimization_config)

    assert len(problem.preassigned_unserved) == 1
    assert problem.preassigned_unserved[0].order_id == "ORD001"
    assert "compartment capacity" in problem.preassigned_unserved[0].reason


def test_preprocessing_prefers_smaller_compartment_size_when_shipment_count_is_equal(
    configured_modules, sample_payload
):
    sample_payload["available_trucks"][1]["compartments"] = [
        {"compartment_id": "C1", "capacity_kl": 10},
        {"compartment_id": "C2", "capacity_kl": 6},
    ]
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    service = PreprocessingService()

    problem = service.preprocess(payload, payload.optimization_config)

    assert [shipment.demand_kl for shipment in problem.shipments if shipment.parent_order_id == "ORD001"] == [8, 8]


def test_preprocessing_uses_spbu_node_time_window_as_constraint_source(
    configured_modules, sample_payload, monkeypatch
):
    monkeypatch.setattr(
        master_data_module,
        "MOCK_SPBU",
        [
            {
                "spbu_id": "SPBU001",
                "name": "SPBU A",
                "lat": -6.11,
                "lng": 106.71,
                "time_window_start": "10:00",
                "time_window_end": "12:00",
                "truck_category": 4,
                "allowed_truck_types": ["SMALL", "MEDIUM", "LARGE"],
            },
            {
                "spbu_id": "SPBU002",
                "name": "SPBU B",
                "lat": -6.12,
                "lng": 106.72,
                "time_window_start": "09:00",
                "time_window_end": "16:00",
                "truck_category": 4,
                "allowed_truck_types": ["SMALL", "MEDIUM", "LARGE"],
            },
        ],
    )
    sample_payload["orders"][0]["time_window_start"] = "06:00"
    sample_payload["orders"][0]["time_window_end"] = "23:00"
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    service = PreprocessingService()

    problem = service.preprocess(payload, payload.optimization_config)

    shipment = next(item for item in problem.shipments if item.parent_order_id == "ORD001")
    assert shipment.time_window_start == 600
    assert shipment.time_window_end == 720


def test_preprocessing_carries_priority_eta_to_shipments(configured_modules, sample_payload):
    sample_payload["orders"][0]["priority"] = True
    sample_payload["orders"][0]["eta"] = "09:30"
    sample_payload["orders"][0]["demand_kl"] = 20
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    service = PreprocessingService()

    problem = service.preprocess(payload, payload.optimization_config)

    ord001_shipments = [item for item in problem.shipments if item.parent_order_id == "ORD001"]
    assert len(ord001_shipments) == 3
    assert all(item.priority is True for item in ord001_shipments)
    assert all(item.priority_eta_minutes == 570 for item in ord001_shipments)


def test_preprocessing_fails_when_distance_matrix_is_unavailable_from_network_master_data(
    configured_modules, sample_payload
):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)

    class _StubNetworkClient:
        def get_time_matrix(self, depot_id: str, spbu_ids: list[str]) -> schemas.MatrixResponse:
            return schemas.MatrixResponse(nodes=["DEPOT", *spbu_ids], matrix=[[0, 10, 20], [10, 0, 5], [20, 5, 0]])

        def get_distance_matrix(self, _depot_id: str, _spbu_ids: list[str]) -> schemas.MatrixResponse:
            raise NetworkDataError("No graph path found in SPBU network master data between DPT001 and SPBU002.")

    service = PreprocessingService(network_client=_StubNetworkClient())

    with pytest.raises(
        ValueError,
        match="Distance matrix from SPBU network master data is unavailable for depot DPT001",
    ):
        service.preprocess(payload, payload.optimization_config)


class _ConstantMatrixNetworkClient:
    def get_time_matrix(self, _depot_id: str, spbu_ids: list[str]) -> schemas.MatrixResponse:
        size = len(spbu_ids) + 1
        matrix = [[0 for _ in range(size)] for _ in range(size)]
        for index in range(1, size):
            matrix[0][index] = 60
            matrix[index][0] = 60
        return schemas.MatrixResponse(nodes=["DEPOT", *spbu_ids], matrix=matrix)

    def get_distance_matrix(self, _depot_id: str, spbu_ids: list[str]) -> schemas.MatrixResponse:
        size = len(spbu_ids) + 1
        matrix = [[0 for _ in range(size)] for _ in range(size)]
        for index in range(1, size):
            matrix[0][index] = 10
            matrix[index][0] = 10
        return schemas.MatrixResponse(nodes=["DEPOT", *spbu_ids], matrix=matrix)


def test_preprocessing_builds_reload_slots_per_vehicle_from_working_horizon(
    configured_modules,
    monkeypatch,
):
    monkeypatch.setattr(
        master_data_module,
        "MOCK_SPBU",
        [
            {
                "spbu_id": "SPBU001",
                "name": "SPBU A",
                "lat": -6.11,
                "lng": 106.71,
                "time_window_start": "06:00",
                "time_window_end": "10:00",
                "truck_category": 4,
                "allowed_truck_types": ["SMALL"],
            }
        ],
    )
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "time_window_start", "06:00")
    monkeypatch.setitem(master_data_module.MOCK_DEPOTS[0], "time_window_end", "10:00")

    payload = schemas.OptimizationRequest.model_validate(
        {
            "dispatch_date": "2026-02-10",
            "depot_id": "DPT001",
            "depot_service_time_minutes": 0,
            "orders": [
                {
                    "order_id": f"ORD{index:03d}",
                    "spbu_id": "SPBU001",
                    "product_type": "PERTALITE",
                    "demand_kl": 10,
                    "priority": False,
                    "eta": None,
                    "service_time_minutes": 0,
                    "time_window_start": "06:00",
                    "time_window_end": "10:00",
                }
                for index in range(1, 9)
            ],
            "available_trucks": [
                {
                    "truck_id": f"TRK{index:03d}",
                    "truck_type": "SMALL",
                    "truck_category": 2,
                    "capacity_kl": 10,
                    "compartments": [{"compartment_id": "C1", "capacity_kl": 10}],
                    "fixed_cost": 1000,
                    "variable_cost_per_km": 10,
                    "variable_cost_per_minute": 2,
                    "start_depot_id": "DPT001",
                    "end_depot_id": "DPT001",
                    "shift_start": "06:00",
                    "shift_end": "10:00",
                    "compatible_product_types": ["PERTALITE"],
                }
                for index in range(1, 5)
            ],
            "optimization_config": {
                "primary_objective": "minimize_truck_count",
                "allow_unserved_fallback": True,
                "minimize_truck_count": True,
                "minimize_distance": True,
                "minimize_time": True,
                "minimize_depot_operation_time": False,
                "objective_priority": [],
                "hard_constraints": {
                    "capacity_limit": True,
                    "time_window": True,
                    "priority_eta": True,
                    "truck_category": True,
                    "depot_operation_window": True,
                    "max_route_duration": False,
                    "max_vehicle_working_time": True,
                    "max_total_distance_per_vehicle": False,
                },
                "soft_constraints": {
                    "allow_unserved_orders": True,
                    "allow_overtime": True,
                    "priority_eta": False,
                    "truck_category": False,
                    "depot_operation_window": False,
                },
                "penalties": {
                    "unserved_order_penalty": 100000,
                    "late_arrival_penalty_per_minute": 100,
                    "priority_eta_penalty_per_minute": 200,
                    "overtime_penalty_per_minute": 50,
                    "depot_operation_window_penalty_per_minute": 50,
                    "capacity_violation_penalty": 0,
                    "activation_cost_vehicle": 10000,
                    "distance_weight": 1,
                    "time_weight": 1,
                    "depot_operation_time_weight": 1,
                },
                "solver_options": {
                    "max_solver_seconds": 10,
                    "first_solution_strategy": "PARALLEL_CHEAPEST_INSERTION",
                    "local_search_metaheuristic": "GUIDED_LOCAL_SEARCH",
                },
                "max_route_duration_minutes": None,
                "max_vehicle_working_time_minutes": 240,
                "max_total_distance_per_vehicle_km": None,
                "max_lateness_minutes": None,
            },
        }
    )

    problem = PreprocessingService(network_client=_ConstantMatrixNetworkClient()).preprocess(
        payload,
        payload.optimization_config,
    )

    assert len(problem.shipments) == 8
    assert len(problem.reload_nodes) == 4
    assert all(node.reload_trip_number == 2 for node in problem.reload_nodes)
