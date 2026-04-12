"""API tests for settings and optimize endpoints."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from app.api.routes import version as version_route
from app.models import schemas
from app.services.scenario_analysis_service import _ExperimentRun, ScenarioAnalysisService


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


def test_version_endpoint_returns_repository_metadata(client, monkeypatch):
    monkeypatch.setattr(
        version_route,
        "get_repository_versions",
        lambda: schemas.RepositoryVersionResponse(
            generated_at=datetime(2026, 4, 12, 2, 0, tzinfo=timezone.utc),
            repositories=[
                schemas.RepositoryVersionItem(
                    key="vrp_planner",
                    title="VRP Planner",
                    repo_name="vrp_planner",
                    branch="main",
                    commit_hash="ff7269a5db68ffd8526a91f5e87f754adf4bb531",
                    short_commit_hash="ff7269a",
                    commit_message="Implement full-service solver pipeline and update docs",
                    committed_at=datetime(2026, 4, 11, 6, 13, 20, tzinfo=timezone.utc),
                    dirty=True,
                    source="git",
                ),
                schemas.RepositoryVersionItem(
                    key="vrp_infa",
                    title="VRP Infra",
                    repo_name="vrp_infa",
                    available=False,
                    source="unavailable",
                    error="Git metadata tidak tersedia di runtime app.",
                ),
            ],
        ),
    )

    response = client.get("/api/v1/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["repositories"][0]["key"] == "vrp_planner"
    assert payload["repositories"][0]["short_commit_hash"] == "ff7269a"
    assert payload["repositories"][0]["dirty"] is True
    assert payload["repositories"][1]["available"] is False


def test_optimize_endpoint_and_scenario_detail(client, sample_payload):
    optimize_response = client.post("/api/v1/optimize", json=sample_payload)
    assert optimize_response.status_code == 202
    body = optimize_response.json()
    assert body["scenario_id"]
    assert body["status"] == "processing"

    list_response = client.get("/api/v1/scenarios")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1
    assert list_response.json()["items"][0]["status"] in {"feasible", "partial"}
    assert "total_demand" in list_response.json()["items"][0]
    assert "total_delivered_demand" in list_response.json()["items"][0]

    detail_response = client.get(f"/api/v1/scenarios/{body['scenario_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["scenario_id"] == body["scenario_id"]
    assert "route_details" in detail
    assert detail["depot_service_time_minutes"] == sample_payload["depot_service_time_minutes"]
    assert "total_depot_operation_time_minutes" in detail
    assert detail["input_trucks"][0]["compartments"]
    assert detail["input_trucks"][0]["truck_category"] == sample_payload["available_trucks"][0]["truck_category"]


def test_scenario_analysis_lifecycle(client, sample_payload):
    optimize_response = client.post("/api/v1/optimize", json=sample_payload)
    scenario_id = optimize_response.json()["scenario_id"]

    create_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/analysis",
        json={"level": "level_1"},
    )
    assert create_response.status_code == 202
    job = create_response.json()
    assert job["analysis_id"]
    assert job["level"] == "level_1"

    list_response = client.get(f"/api/v1/scenarios/{scenario_id}/analysis")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "completed"

    detail_response = client.get(
        f"/api/v1/scenarios/{scenario_id}/analysis/{job['analysis_id']}"
    )
    assert detail_response.status_code == 200
    analysis = detail_response.json()
    assert analysis["status"] == "completed"
    assert analysis["report"]["root_cause_summary"]
    assert isinstance(analysis["report"]["problematic_orders"], list)

    overview_response = client.get("/api/v1/scenarios/analysis/jobs")
    assert overview_response.status_code == 200
    overview_items = overview_response.json()["items"]
    assert len(overview_items) == 1
    assert overview_items[0]["analysis_id"] == job["analysis_id"]
    assert overview_items[0]["scenario_id"] == scenario_id


def test_level_two_analysis_reports_experiment_costs(client, sample_payload, monkeypatch):
    def fake_run_experiment(
        self,
        scenario_id,
        payload,
        config,
        experiment_id,
        title,
        changed_assumptions,
    ):
        summary = schemas.ScenarioAnalysisExperimentResult(
            experiment_id=experiment_id,
            title=title,
            summary="Synthetic experiment result.",
            scenario_status="feasible",
            solver_status="ROUTING_SUCCESS",
            assignment_found=True,
            total_unserved_orders=0,
            total_cost=123456.0,
            solver_runtime_seconds=0.12,
            changed_assumptions=changed_assumptions,
        )
        result = schemas.OptimizationResultResponse(
            scenario_id=scenario_id,
            status="feasible",
            message="Synthetic experiment result.",
            total_orders=len(payload.orders),
            total_demand=sum(order.demand_kl for order in payload.orders),
            total_delivered_demand=sum(order.demand_kl for order in payload.orders),
            total_unserved_orders=0,
            active_truck_count=1,
            active_truck_type_summary=[],
            total_distance=10,
            total_time=20,
            total_cost=123456.0,
            total_penalty=0,
            cost_breakdown=schemas.CostBreakdown(
                activation_cost_total=0,
                distance_cost_total=10,
                time_cost_total=20,
                depot_operation_cost_total=0,
                late_arrival_penalty_total=0,
                priority_eta_penalty_total=0,
                overtime_penalty_total=0,
                max_total_distance_penalty_total=0,
                unserved_penalty_total=0,
                depot_operation_window_penalty_total=0,
                total_penalty_cost=0,
                total_cost=123456.0,
            ),
            total_depot_operation_time_minutes=0,
            depot_operation_start=None,
            depot_operation_end=None,
            solver_runtime_seconds=0.12,
            objective_config=config,
            route_details=[],
            unserved_orders=[],
            preprocessing_notes=[],
        )
        return _ExperimentRun(summary=summary, result=result)

    monkeypatch.setattr(ScenarioAnalysisService, "_run_experiment", fake_run_experiment)

    optimize_response = client.post("/api/v1/optimize", json=sample_payload)
    scenario_id = optimize_response.json()["scenario_id"]

    create_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/analysis",
        json={"level": "level_2"},
    )
    assert create_response.status_code == 202
    analysis_id = create_response.json()["analysis_id"]

    detail_response = client.get(
        f"/api/v1/scenarios/{scenario_id}/analysis/{analysis_id}"
    )
    assert detail_response.status_code == 200
    analysis = detail_response.json()
    assert analysis["status"] == "completed"

    experiment_results = analysis["report"]["experiment_results"]
    assert len(experiment_results) >= 2
    assert all(item["scenario_status"] != "error" for item in experiment_results)
    assert all(item["solver_status"] != "EXPERIMENT_ERROR" for item in experiment_results)
    assert all("total_cost" in item for item in experiment_results)
    assert all(item["total_cost"] >= 0 for item in experiment_results)


def test_level_one_analysis_explains_preprocessing_failure(client, sample_payload):
    payload = deepcopy(sample_payload)
    for order in payload["orders"]:
        order["spbu_id"] = "SPBU001"
    for truck in payload["available_trucks"]:
        truck["truck_category"] = 4

    optimize_response = client.post("/api/v1/optimize", json=payload)
    assert optimize_response.status_code == 202
    scenario_id = optimize_response.json()["scenario_id"]

    detail_response = client.get(f"/api/v1/scenarios/{scenario_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "preprocessing_failed"
    assert detail["total_delivered_demand"] == 0
    assert detail["message"] == "No feasible shipments remained after preprocessing."

    create_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/analysis",
        json={"level": "level_1"},
    )
    assert create_response.status_code == 202
    analysis_id = create_response.json()["analysis_id"]

    analysis_response = client.get(
        f"/api/v1/scenarios/{scenario_id}/analysis/{analysis_id}"
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()
    assert analysis["report"]["root_cause_summary"].startswith(
        "Scenario gagal di preprocessing sehingga seluruh order ditandai unserved"
    )
    assert "Status preprocessing failed" in analysis["report"]["solver_status_explained"]
    assert any(
        "No truck matches SPBU truck category policy." in item
        for item in analysis["report"]["key_findings"]
    )
