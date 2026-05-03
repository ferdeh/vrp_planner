"""Unit tests for RouteFinder hybrid orchestration."""

from __future__ import annotations

import httpx

from app.models import schemas
from app.repositories.scenario_repository import ScenarioRepository
from app.schemas.canonical_vrp_schema import (
    CanonicalConstraints,
    CanonicalMatrices,
    CanonicalNode,
    CanonicalOrder,
    CanonicalScenario,
    CanonicalSettings,
    CanonicalVRPModel,
)
from app.schemas.routefinder_cluster_schema import Cluster, ClusterResult
from app.schemas.solver_setting_schema import SolverSettings
from app.services.initial_solution_validator import InitialSolutionValidator
from app.services.optimization_service import OptimizationService
from app.services.preprocessing_service import PreprocessingService
from app.services.routefinder_client import RouteFinderClient
from app.services.solution_validator import SolutionValidator
from app.services.solver_orchestrator import SolverOrchestrator
from app.solver.ortools_solver import OrToolsSolver


class _TimeoutingHttpClient:
    def post(self, *_args, **_kwargs):
        raise httpx.TimeoutException("timed out")


class _ObservingSolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def solve(self, problem, warm_start_routes=None):
        self.calls.append(
            {
                "warm_start_routes": warm_start_routes,
                "cluster_mode": problem.cluster_mode,
                "clusters": [shipment.cluster_id for shipment in problem.shipments],
            }
        )
        return OrToolsSolver().solve(problem, warm_start_routes=warm_start_routes)


def _single_stop_result(
    payload: schemas.OptimizationRequest,
    *,
    truck_id: str,
    order_id: str,
    spbu_id: str,
    eta: str,
    route_time: float = 90,
) -> schemas.OptimizationResultResponse:
    order = next(item for item in payload.orders if item.order_id == order_id)
    truck = next(item for item in payload.available_trucks if item.truck_id == truck_id)
    return schemas.OptimizationResultResponse(
        scenario_id="00000000-0000-0000-0000-000000000999",
        status="partial",
        message="Synthetic validation result.",
        total_orders=len(payload.orders),
        total_demand=sum(item.demand_kl for item in payload.orders),
        total_delivered_demand=order.demand_kl,
        total_unserved_orders=len(payload.orders) - 1,
        active_truck_count=1,
        active_truck_type_summary=[],
        total_distance=10,
        total_time=route_time,
        total_cost=10,
        total_penalty=0,
        solver_runtime_seconds=0.01,
        objective_config=payload.optimization_config,
        route_details=[
            schemas.RouteDetailResponse(
                truck_id=truck_id,
                truck_type=truck.truck_type,
                capacity_kl=truck.capacity_kl,
                total_load=order.demand_kl,
                utilization_percent=round((order.demand_kl / truck.capacity_kl) * 100, 2),
                route_distance=10,
                route_time=route_time,
                stop_count=1,
                trip_count=1,
                return_eta=eta,
                stops=[
                    schemas.RouteStopResponse(
                        sequence=1,
                        order_id=order_id,
                        parent_order_id=order_id,
                        spbu_id=spbu_id,
                        eta=eta,
                        etd=eta,
                        delivered_volume=order.demand_kl,
                        arrival_status="late",
                    )
                ],
            )
        ],
        unserved_orders=[
            schemas.UnservedOrderDetail(
                order_id=item.order_id,
                parent_order_id=item.order_id,
                spbu_id=item.spbu_id,
                demand_kl=item.demand_kl,
                reason="Synthetic unserved order for validator test.",
            )
            for item in payload.orders
            if item.order_id != order_id
        ],
        preprocessing_notes=[],
    )


def _build_canonical_model() -> CanonicalVRPModel:
    return CanonicalVRPModel(
        scenario=CanonicalScenario(
            scenario_id="scenario-1",
            planning_date="2026-02-10",
            depot_codes=["DPT001"],
        ),
        nodes=[
            CanonicalNode(
                node_id="DPT001",
                node_code="DPT001",
                node_name="Depot A",
                node_type="depot",
            ),
            CanonicalNode(
                node_id="SPBU001",
                node_code="SPBU001",
                node_name="SPBU A",
                node_type="spbu",
            ),
        ],
        vehicles=[],
        orders=[
            CanonicalOrder(
                order_id="ORD001",
                parent_order_id="ORD001",
                node_id="SPBU001",
                product_code="PERTALITE",
                quantity_kl=8,
                service_time_minutes=30,
            )
        ],
        matrices=CanonicalMatrices(
            distance_matrix=[[0, 10], [10, 0]],
            duration_matrix=[[0, 15], [15, 0]],
            node_ids=["DPT001", "SPBU001"],
        ),
        constraints=CanonicalConstraints(),
        settings=CanonicalSettings(),
    )


def test_routefinder_client_handles_timeout_error():
    client = RouteFinderClient(service_url="http://routefinder", http_client=_TimeoutingHttpClient())

    with httpx.Client():
        try:
            client.generate_clusters(_build_canonical_model())
        except Exception as exc:
            assert str(exc) == "RouteFinder request timed out."
        else:
            raise AssertionError("Expected RouteFinder timeout exception.")


def test_initial_solution_validator_rejects_invalid_routes(configured_modules, sample_payload):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    routes = [[problem.shipments[0].node_index, problem.shipments[0].node_index], []]

    validation = InitialSolutionValidator().validate(problem, routes)

    assert validation.is_valid is False
    assert any("duplicated" in error for error in validation.errors)


def test_solver_orchestrator_falls_back_to_ortools_when_routefinder_fails(
    configured_modules,
    sample_payload,
):
    _, database_module, _ = configured_modules
    db = database_module.SessionLocal()
    try:
        payload = schemas.OptimizationRequest.model_validate(sample_payload)
        payload = payload.model_copy(update={"solver_settings": SolverSettings(use_routefinder=True)})
        scenario = ScenarioRepository(db).create_scenario_snapshot(payload)
        observing_solver = _ObservingSolver()
        orchestrator = SolverOrchestrator(
            db,
            solver=observing_solver,
        )
        orchestrator.routefinder_client.generate_clusters = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("RouteFinder unavailable")
        )

        result = orchestrator.solve(
            scenario=scenario,
            payload=payload,
            merged_config=payload.optimization_config,
        )

        assert result.status in {"feasible", "partial"}
        assert observing_solver.calls[0]["warm_start_routes"] is None
        assert observing_solver.calls[0]["clusters"] == [None, None, None]
    finally:
        db.close()


def test_solver_orchestrator_applies_clusters_when_routefinder_valid(
    configured_modules,
    sample_payload,
):
    _, database_module, _ = configured_modules
    db = database_module.SessionLocal()
    try:
        payload = schemas.OptimizationRequest.model_validate(sample_payload)
        payload = payload.model_copy(
            update={"solver_settings": SolverSettings(use_routefinder=True, cluster_mode="hard", max_cluster_size=5)}
        )
        scenario = ScenarioRepository(db).create_scenario_snapshot(payload)
        observing_solver = _ObservingSolver()
        orchestrator = SolverOrchestrator(
            db,
            solver=observing_solver,
        )
        orchestrator.routefinder_client.generate_clusters = lambda *_args, **_kwargs: (
            ClusterResult(
                clusters=[
                    Cluster(
                        cluster_id="CL-001",
                        spbu_ids=["SPBU001", "SPBU002"],
                        total_demand_kl=24,
                    )
                ],
            ),
            0.01,
        )

        result = orchestrator.solve(
            scenario=scenario,
            payload=payload,
            merged_config=payload.optimization_config,
        )

        assert result.status in {"feasible", "partial"}
        assert observing_solver.calls[0]["warm_start_routes"] is None
        assert observing_solver.calls[0]["cluster_mode"] == "hard"
        assert observing_solver.calls[0]["clusters"] == ["CL-001", "CL-001", "CL-001"]
    finally:
        db.close()


def test_solution_validator_treats_max_working_time_as_soft_constraint(
    configured_modules,
    sample_payload,
):
    payload_data = {
        **sample_payload,
        "optimization_config": {
            **sample_payload["optimization_config"],
            "hard_constraints": {
                **sample_payload["optimization_config"]["hard_constraints"],
                "max_vehicle_working_time": False,
            },
            "soft_constraints": {
                **sample_payload["optimization_config"]["soft_constraints"],
                "allow_overtime": True,
                "max_vehicle_working_time": True,
            },
        },
    }
    payload = schemas.OptimizationRequest.model_validate(payload_data)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = schemas.OptimizationResultResponse(
        scenario_id="00000000-0000-0000-0000-000000000001",
        status="partial",
        message="Soft overtime allowed.",
        total_orders=len(payload.orders),
        total_demand=sum(order.demand_kl for order in payload.orders),
        total_delivered_demand=sum(order.demand_kl for order in payload.orders),
        total_unserved_orders=0,
        active_truck_count=1,
        active_truck_type_summary=[],
        total_distance=10,
        total_time=810,
        total_cost=10,
        total_penalty=4500,
        solver_runtime_seconds=0.01,
        objective_config=payload.optimization_config,
        route_details=[
            schemas.RouteDetailResponse(
                truck_id="TRK001",
                truck_type="SMALL",
                capacity_kl=8,
                total_load=24,
                utilization_percent=100,
                route_distance=10,
                route_time=810,
                stop_count=5,
                trip_count=1,
                return_eta="19:30",
                stops=[
                    schemas.RouteStopResponse(
                        sequence=1,
                        order_id="ORD001",
                        parent_order_id="ORD001",
                        spbu_id="SPBU001",
                        eta="08:00",
                        etd="08:30",
                        delivered_volume=8,
                        arrival_status="on_time",
                    ),
                    schemas.RouteStopResponse(
                        sequence=2,
                        order_id="RELOAD-1",
                        parent_order_id="RELOAD-1",
                        spbu_id=payload.depot_id,
                        stop_kind="depot_reload",
                        eta="12:00",
                        etd="12:30",
                        delivered_volume=0,
                        arrival_status="on_time",
                    ),
                    schemas.RouteStopResponse(
                        sequence=3,
                        order_id="ORD001",
                        parent_order_id="ORD001",
                        spbu_id="SPBU001",
                        eta="13:00",
                        etd="13:30",
                        delivered_volume=8,
                        arrival_status="on_time",
                    ),
                    schemas.RouteStopResponse(
                        sequence=4,
                        order_id="RELOAD-2",
                        parent_order_id="RELOAD-2",
                        spbu_id=payload.depot_id,
                        stop_kind="depot_reload",
                        eta="14:00",
                        etd="14:30",
                        delivered_volume=0,
                        arrival_status="on_time",
                    ),
                    schemas.RouteStopResponse(
                        sequence=5,
                        order_id="ORD002",
                        parent_order_id="ORD002",
                        spbu_id="SPBU002",
                        eta="15:00",
                        etd="15:25",
                        delivered_volume=8,
                        arrival_status="on_time",
                    ),
                ],
            )
        ],
        unserved_orders=[],
        preprocessing_notes=[],
    )

    validation = SolutionValidator().validate(
        payload=payload,
        problem=problem,
        result=result,
    )

    assert validation.is_valid is True
    assert validation.hard_constraint_violations == {}
    assert validation.soft_constraint_penalties["max_vehicle_working_time"] == 90


def test_solution_validator_rejects_max_working_time_when_hard_constraint_enabled(
    configured_modules,
    sample_payload,
):
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = schemas.OptimizationResultResponse(
        scenario_id="00000000-0000-0000-0000-000000000002",
        status="partial",
        message="Hard overtime should fail.",
        total_orders=len(payload.orders),
        total_demand=sum(order.demand_kl for order in payload.orders),
        total_delivered_demand=sum(order.demand_kl for order in payload.orders),
        total_unserved_orders=0,
        active_truck_count=1,
        active_truck_type_summary=[],
        total_distance=10,
        total_time=810,
        total_cost=10,
        total_penalty=0,
        solver_runtime_seconds=0.01,
        objective_config=payload.optimization_config,
        route_details=[
            schemas.RouteDetailResponse(
                truck_id="TRK001",
                truck_type="SMALL",
                capacity_kl=8,
                total_load=24,
                utilization_percent=100,
                route_distance=10,
                route_time=810,
                stop_count=5,
                trip_count=1,
                return_eta="19:30",
                stops=[
                    schemas.RouteStopResponse(
                        sequence=1,
                        order_id="ORD001",
                        parent_order_id="ORD001",
                        spbu_id="SPBU001",
                        eta="08:00",
                        etd="08:30",
                        delivered_volume=8,
                        arrival_status="on_time",
                    ),
                    schemas.RouteStopResponse(
                        sequence=2,
                        order_id="RELOAD-1",
                        parent_order_id="RELOAD-1",
                        spbu_id=payload.depot_id,
                        stop_kind="depot_reload",
                        eta="12:00",
                        etd="12:30",
                        delivered_volume=0,
                        arrival_status="on_time",
                    ),
                    schemas.RouteStopResponse(
                        sequence=3,
                        order_id="ORD001",
                        parent_order_id="ORD001",
                        spbu_id="SPBU001",
                        eta="13:00",
                        etd="13:30",
                        delivered_volume=8,
                        arrival_status="on_time",
                    ),
                    schemas.RouteStopResponse(
                        sequence=4,
                        order_id="RELOAD-2",
                        parent_order_id="RELOAD-2",
                        spbu_id=payload.depot_id,
                        stop_kind="depot_reload",
                        eta="14:00",
                        etd="14:30",
                        delivered_volume=0,
                        arrival_status="on_time",
                    ),
                    schemas.RouteStopResponse(
                        sequence=5,
                        order_id="ORD002",
                        parent_order_id="ORD002",
                        spbu_id="SPBU002",
                        eta="15:00",
                        etd="15:25",
                        delivered_volume=8,
                        arrival_status="on_time",
                    ),
                ],
            )
        ],
        unserved_orders=[],
        preprocessing_notes=[],
    )

    validation = SolutionValidator().validate(
        payload=payload,
        problem=problem,
        result=result,
    )

    assert validation.is_valid is False
    assert validation.soft_constraint_penalties == {}
    assert validation.hard_constraint_violations["max_working_minutes"] == [
        {
            "truck_id": "TRK001",
            "route_time": 810.0,
            "max_working_minutes": 720,
        }
    ]


def test_solution_validator_ignores_time_window_when_constraint_is_off(
    configured_modules,
    sample_payload,
):
    payload_data = {
        **sample_payload,
        "optimization_config": {
            **sample_payload["optimization_config"],
            "hard_constraints": {
                **sample_payload["optimization_config"]["hard_constraints"],
                "time_window": False,
            },
            "soft_constraints": {
                **sample_payload["optimization_config"]["soft_constraints"],
                "time_window": False,
            },
        },
    }
    payload = schemas.OptimizationRequest.model_validate(payload_data)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = _single_stop_result(
        payload,
        truck_id="TRK001",
        order_id="ORD002",
        spbu_id="SPBU002",
        eta="16:30",
    )

    validation = SolutionValidator().validate(
        payload=payload,
        problem=problem,
        result=result,
    )

    assert validation.is_valid is True
    assert "time_window" not in validation.hard_constraint_violations
    assert "time_window" not in validation.soft_constraint_penalties


def test_solution_validator_rejects_priority_eta_when_hard_constraint_enabled(
    configured_modules,
    sample_payload,
):
    sample_payload["orders"] = [sample_payload["orders"][0]]
    sample_payload["orders"][0]["demand_kl"] = 8
    sample_payload["orders"][0]["priority"] = True
    sample_payload["orders"][0]["eta"] = "14:00"
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = _single_stop_result(
        payload,
        truck_id="TRK001",
        order_id="ORD001",
        spbu_id="SPBU001",
        eta="14:30",
    )

    validation = SolutionValidator().validate(
        payload=payload,
        problem=problem,
        result=result,
    )

    assert validation.is_valid is False
    assert validation.hard_constraint_violations["priority_eta"] == [
        {
            "order_id": "ORD001",
            "eta": "14:30",
            "priority_eta": "14:00",
        }
    ]


def test_solution_validator_ignores_priority_eta_when_constraint_is_off(
    configured_modules,
    sample_payload,
):
    sample_payload["orders"] = [sample_payload["orders"][0]]
    sample_payload["orders"][0]["demand_kl"] = 8
    sample_payload["orders"][0]["priority"] = True
    sample_payload["orders"][0]["eta"] = "14:00"
    sample_payload["optimization_config"]["hard_constraints"]["priority_eta"] = False
    sample_payload["optimization_config"]["soft_constraints"]["priority_eta"] = False
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = _single_stop_result(
        payload,
        truck_id="TRK001",
        order_id="ORD001",
        spbu_id="SPBU001",
        eta="14:30",
    )

    validation = SolutionValidator().validate(
        payload=payload,
        problem=problem,
        result=result,
    )

    assert validation.is_valid is True
    assert "priority_eta" not in validation.hard_constraint_violations
    assert "priority_eta" not in validation.soft_constraint_penalties


def test_solution_validator_ignores_truck_category_when_constraint_is_off(
    configured_modules,
    sample_payload,
):
    sample_payload["orders"][0]["demand_kl"] = 8
    sample_payload["optimization_config"]["hard_constraints"]["truck_category"] = False
    sample_payload["optimization_config"]["soft_constraints"]["truck_category"] = False
    payload = schemas.OptimizationRequest.model_validate(sample_payload)
    problem = PreprocessingService().preprocess(payload, payload.optimization_config)
    result = _single_stop_result(
        payload,
        truck_id="TRK002",
        order_id="ORD001",
        spbu_id="SPBU001",
        eta="10:00",
    )

    validation = SolutionValidator().validate(
        payload=payload,
        problem=problem,
        result=result,
    )

    assert validation.is_valid is True
    assert "truck_category" not in validation.hard_constraint_violations
