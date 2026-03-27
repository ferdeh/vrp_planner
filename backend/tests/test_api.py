"""API tests for settings and optimize endpoints."""

from __future__ import annotations


def test_settings_update_roundtrip(client):
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    payload = response.json()
    payload["default_optimization_config"]["solver_options"]["max_solver_seconds"] = 42

    update_response = client.put(
        "/api/v1/settings",
        json={
            "default_optimization_config": payload["default_optimization_config"],
            "ui_preferences": {"theme": "ops"},
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["default_optimization_config"]["solver_options"]["max_solver_seconds"] == 42


def test_optimize_endpoint_and_scenario_detail(client, sample_payload):
    optimize_response = client.post("/api/v1/optimize", json=sample_payload)
    assert optimize_response.status_code == 200
    body = optimize_response.json()
    assert body["scenario_id"]
    assert body["status"] in {"feasible", "partial"}

    list_response = client.get("/api/v1/scenarios")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1

    detail_response = client.get(f"/api/v1/scenarios/{body['scenario_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["scenario_id"] == body["scenario_id"]
    assert "route_details" in detail
    assert detail["depot_service_time_minutes"] == sample_payload["depot_service_time_minutes"]
    assert "total_depot_operation_time_minutes" in detail
    assert detail["input_trucks"][0]["compartments"]
    assert detail["input_trucks"][0]["truck_category"] == sample_payload["available_trucks"][0]["truck_category"]
