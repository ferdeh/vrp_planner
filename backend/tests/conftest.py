"""Shared pytest fixtures."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def sample_payload() -> dict:
    return {
        "dispatch_date": "2026-02-10",
        "depot_id": "DPT001",
        "depot_service_time_minutes": 0,
        "orders": [
            {
                "order_id": "ORD001",
                "spbu_id": "SPBU001",
                "product_type": "PERTALITE",
                "demand_kl": 16,
                "priority": False,
                "eta": None,
                "service_time_minutes": 30,
                "time_window_start": "08:00",
                "time_window_end": "15:00",
            },
            {
                "order_id": "ORD002",
                "spbu_id": "SPBU002",
                "product_type": "PERTALITE",
                "demand_kl": 8,
                "priority": False,
                "eta": None,
                "service_time_minutes": 25,
                "time_window_start": "09:00",
                "time_window_end": "16:00",
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
                "compatible_product_types": ["PERTALITE", "PERTAMAX"],
            },
            {
                "truck_id": "TRK002",
                "truck_type": "MEDIUM",
                "truck_category": 3,
                "capacity_kl": 16,
                "compartments": [
                    {"compartment_id": "C1", "capacity_kl": 8},
                    {"compartment_id": "C2", "capacity_kl": 8},
                ],
                "fixed_cost": 1800,
                "variable_cost_per_km": 12,
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


@pytest.fixture()
def configured_modules(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("USE_MOCK_MASTER_DATA", "true")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MASTER_DATA_API_BASE_URL", "http://spbu-backend:8000")

    from app.core import config as config_module
    from app.core import database as database_module

    config_module.get_settings.cache_clear()
    database_module.refresh_engine()

    import app.main as main_module

    importlib.reload(main_module)
    database_module.Base.metadata.drop_all(bind=database_module.get_engine())
    database_module.Base.metadata.create_all(bind=database_module.get_engine())
    return config_module, database_module, main_module


@pytest.fixture()
def client(configured_modules):
    _, _, main_module = configured_modules
    with TestClient(main_module.app) as test_client:
        yield test_client
