"""Tests for preprocessing service."""

from __future__ import annotations

from app.models import schemas
from app.services import master_data_client as master_data_module
from app.services.preprocessing_service import PreprocessingService


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
