"""Pydantic schemas for API and service boundaries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


SolutionStatus = Literal[
    "processing",
    "feasible",
    "infeasible",
    "partial",
    "preprocessing_failed",
    "timeout",
    "error",
]
AnalysisLevel = Literal["level_1", "level_2"]
AnalysisStatus = Literal["processing", "completed", "error"]
SUPPORTED_PRODUCT_TYPES = [
    "PERTALITE",
    "PERTAMAX",
    "PERTAMAX_TURBO",
    "PERTAMAX_GREEN",
    "BIO_SOLAR",
    "DEXLITE",
    "PERTAMINA_DEX",
]
SUPPORTED_OBJECTIVE_KEYS = [
    "minimize_truck_count",
    "minimize_distance",
    "minimize_time",
    "minimize_depot_operation_time",
]


class SPBUData(BaseModel):
    spbu_id: str
    name: str
    lat: float
    lng: float
    time_window_start: str
    time_window_end: str
    truck_category: int | None = None
    allowed_truck_types: list[str] = Field(default_factory=list)
    supply_depot_ids: list[str] = Field(default_factory=list)


class DepotData(BaseModel):
    depot_id: str
    name: str
    lat: float
    lng: float
    time_window_start: str = "00:00"
    time_window_end: str = "23:59"
    gate_limit: int | None = None


class NetworkNodeData(BaseModel):
    node_id: str
    node_code: str
    node_name: str
    node_type: str
    lat: float
    lng: float
    layout_x: float | None = None
    layout_y: float | None = None
    truck_category: int | None = None
    is_active: bool = True
    supply_depot_ids: list[str] = Field(default_factory=list)


class EffectiveEdgeData(BaseModel):
    from_node_id: str
    to_node_id: str
    distance_km: float | None = None
    max_velocity_kmh: float | None = None
    source: str | None = None
    road_category: str | None = None


class MatrixResponse(BaseModel):
    nodes: list[str]
    matrix: list[list[int]]


class OrderInput(BaseModel):
    order_id: str
    spbu_id: str
    spbu_name: str | None = None
    product_type: str
    demand_kl: float
    priority: bool = False
    eta: str | None = None
    service_time_minutes: int
    time_window_start: str
    time_window_end: str


class TruckCompartment(BaseModel):
    compartment_id: str
    capacity_kl: float


class TruckInput(BaseModel):
    truck_id: str
    no_polisi: str | None = None
    truck_type: str
    truck_category: int | None = None
    capacity_kl: float
    start_depot_id: str
    end_depot_id: str
    shift_start: str
    shift_end: str
    compatible_product_types: list[str] = Field(default_factory=list)
    compartments: list[TruckCompartment] = Field(default_factory=list)
    status: str | None = None
    not_available_from: str | None = None
    not_available_to: str | None = None

    @model_validator(mode="after")
    def sync_compartments(self) -> "TruckInput":
        self.compatible_product_types = list(SUPPORTED_PRODUCT_TYPES)
        if self.compartments:
            self.capacity_kl = round(sum(item.capacity_kl for item in self.compartments), 6)
        else:
            self.compartments = [TruckCompartment(compartment_id="1", capacity_kl=self.capacity_kl)]
        return self


class TruckMasterData(BaseModel):
    truck_id: str
    no_polisi: str | None = None
    truck_type: str
    truck_category: int | None = None
    capacity_kl: float
    depot_id: str
    shift_start: str
    shift_end: str
    compatible_product_types: list[str] = Field(default_factory=list)
    compartments: list[TruckCompartment] = Field(default_factory=list)
    is_available: bool = True
    depot_code: str | None = None
    depot_name: str | None = None
    status: str | None = None
    not_available_from: str | None = None
    not_available_to: str | None = None

    @model_validator(mode="after")
    def sync_compartments(self) -> "TruckMasterData":
        self.compatible_product_types = list(SUPPORTED_PRODUCT_TYPES)
        if self.compartments:
            self.capacity_kl = round(sum(item.capacity_kl for item in self.compartments), 6)
        else:
            self.compartments = [TruckCompartment(compartment_id="1", capacity_kl=self.capacity_kl)]
        return self


class HardConstraintConfig(BaseModel):
    capacity_limit: bool = True
    time_window: bool = True
    priority_eta: bool = True
    truck_category: bool = True
    no_split_order: bool = False
    depot_operation_window: bool = True
    max_route_duration: bool = False
    max_vehicle_working_time: bool = True
    max_total_distance_per_vehicle: bool = False


class SoftConstraintConfig(BaseModel):
    allow_unserved_orders: bool = True
    allow_overtime: bool = True
    capacity_limit: bool = False
    time_window: bool = False
    priority_eta: bool = False
    truck_category: bool = False
    depot_operation_window: bool = False
    max_route_duration: bool = False
    max_vehicle_working_time: bool = False
    max_total_distance_per_vehicle: bool = False


class PenaltyConfig(BaseModel):
    unserved_order_penalty: float = 100000
    late_arrival_penalty_per_minute: float = 100
    priority_eta_penalty_per_minute: float = 200
    overtime_penalty_per_minute: float = 50
    depot_operation_window_penalty_per_minute: float = 50
    capacity_violation_penalty: float = 0
    activation_cost_vehicle: float = Field(
        default=10000,
        validation_alias=AliasChoices("activation_cost_vehicle", "fixed_cost_vehicle"),
    )
    distance_weight: float = 1
    time_weight: float = 1
    depot_operation_time_weight: float = 1


class SolverOptions(BaseModel):
    max_solver_seconds: int = 30
    first_solution_strategy: str = "PATH_CHEAPEST_ARC"
    local_search_metaheuristic: str = "GUIDED_LOCAL_SEARCH"


class OptimizationConfig(BaseModel):
    minimize_truck_count: bool = True
    minimize_distance: bool = True
    minimize_time: bool = True
    minimize_depot_operation_time: bool = True
    objective_priority: list[str] = Field(default_factory=lambda: list(SUPPORTED_OBJECTIVE_KEYS))
    hard_constraints: HardConstraintConfig = Field(default_factory=HardConstraintConfig)
    soft_constraints: SoftConstraintConfig = Field(default_factory=SoftConstraintConfig)
    penalties: PenaltyConfig = Field(default_factory=PenaltyConfig)
    solver_options: SolverOptions = Field(default_factory=SolverOptions)
    max_route_duration_minutes: int | None = None
    max_vehicle_working_time_minutes: int | None = None
    max_total_distance_per_vehicle_km: int | None = None
    max_lateness_minutes: int | None = None

    @model_validator(mode="after")
    def normalize_objective_priority(self) -> "OptimizationConfig":
        normalized: list[str] = []
        for item in self.objective_priority:
            if item in SUPPORTED_OBJECTIVE_KEYS and item not in normalized:
                normalized.append(item)
        for item in SUPPORTED_OBJECTIVE_KEYS:
            if item not in normalized:
                normalized.append(item)
        self.objective_priority = normalized
        return self


class OptimizationRequest(BaseModel):
    dispatch_date: date
    depot_id: str
    depot_service_time_minutes: int = Field(default=0, ge=0)
    orders: list[OrderInput]
    available_trucks: list[TruckInput]
    optimization_config: OptimizationConfig | None = None

    @field_validator("orders")
    @classmethod
    def ensure_orders(cls, value: list[OrderInput]) -> list[OrderInput]:
        if not value:
            raise ValueError("At least one order is required.")
        return value

    @field_validator("available_trucks")
    @classmethod
    def ensure_trucks(cls, value: list[TruckInput]) -> list[TruckInput]:
        if not value:
            raise ValueError("At least one truck is required.")
        return value


class SystemSettingsPayload(BaseModel):
    default_optimization_config: OptimizationConfig = Field(default_factory=OptimizationConfig)
    ui_preferences: dict[str, Any] = Field(default_factory=dict)


class SystemSettingsResponse(BaseModel):
    id: UUID
    default_optimization_config: OptimizationConfig
    ui_preferences: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PreprocessingNote(BaseModel):
    code: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class UnservedOrderDetail(BaseModel):
    order_id: str
    parent_order_id: str
    spbu_id: str
    demand_kl: float
    reason: str
    constraint_details: list[str] = Field(default_factory=list)


class RouteStopResponse(BaseModel):
    sequence: int
    order_id: str
    parent_order_id: str
    spbu_id: str
    stop_kind: Literal["delivery", "depot_reload", "depot_wait"] = "delivery"
    trip_sequence: int = 1
    spbu_name: str | None = None
    travel_path: str | None = None
    segment_max_velocity_kmh: str | None = None
    travel_distance_km: float | None = None
    travel_time_minutes: float | None = None
    eta: str
    etd: str
    delivered_volume: float
    arrival_status: str


class RouteDetailResponse(BaseModel):
    truck_id: str
    no_polisi: str | None = None
    origin_name: str | None = None
    origin_service_start: str | None = None
    origin_etd: str | None = None
    depot_service_time_minutes: int = 0
    depot_gate_limit: int | None = None
    return_eta: str | None = None
    return_path: str | None = None
    return_segment_max_velocity_kmh: str | None = None
    return_distance_km: float | None = None
    return_travel_time_minutes: float | None = None
    truck_type: str
    capacity_kl: float
    total_load: float
    utilization_percent: float
    route_distance: float
    route_time: float
    stop_count: int
    trip_count: int = 1
    stops: list[RouteStopResponse] = Field(default_factory=list)


class TruckTypeSummary(BaseModel):
    truck_type: str
    active_count: int
    total_capacity_kl: float


class CostBreakdown(BaseModel):
    activation_cost_total: float = 0
    distance_cost_total: float = 0
    time_cost_total: float = 0
    depot_operation_cost_total: float = 0
    late_arrival_penalty_total: float = 0
    priority_eta_penalty_total: float = 0
    overtime_penalty_total: float = 0
    max_total_distance_penalty_total: float = 0
    unserved_penalty_total: float = 0
    depot_operation_window_penalty_total: float = 0
    total_penalty_cost: float = 0
    total_cost: float = 0


class OptimizationResultResponse(BaseModel):
    scenario_id: UUID
    status: SolutionStatus
    message: str
    total_orders: int
    total_demand: float
    total_delivered_demand: float
    total_unserved_orders: int
    active_truck_count: int
    active_truck_type_summary: list[TruckTypeSummary]
    total_distance: float
    total_time: float
    total_cost: float
    total_penalty: float
    cost_breakdown: CostBreakdown = Field(default_factory=CostBreakdown)
    total_depot_operation_time_minutes: int = 0
    depot_operation_start: str | None = None
    depot_operation_end: str | None = None
    solver_runtime_seconds: float
    objective_config: OptimizationConfig
    route_details: list[RouteDetailResponse]
    unserved_orders: list[UnservedOrderDetail]
    preprocessing_notes: list[PreprocessingNote]


class OptimizationJobResponse(BaseModel):
    scenario_id: UUID
    status: SolutionStatus
    message: str
    created_at: datetime


class ScenarioListItem(BaseModel):
    scenario_id: UUID
    dispatch_date: date
    depot_id: str
    status: SolutionStatus
    total_demand: float
    total_delivered_demand: float
    active_truck_count: int
    total_cost: float
    total_distance: float
    total_time: float
    created_at: datetime


class ScenarioDashboardSummary(BaseModel):
    total_scenarios: int
    feasible_scenarios: int
    average_active_trucks: float


class DeleteScenariosRequest(BaseModel):
    scenario_ids: list[UUID] = Field(default_factory=list)

    @field_validator("scenario_ids")
    @classmethod
    def ensure_ids(cls, value: list[UUID]) -> list[UUID]:
        if not value:
            raise ValueError("At least one scenario_id is required.")
        return value


class DeleteScenariosResponse(BaseModel):
    deleted_count: int


class ScenarioDetailResponse(OptimizationResultResponse):
    dispatch_date: date
    depot_id: str
    depot_service_time_minutes: int = 0
    input_orders: list[OrderInput]
    input_trucks: list[TruckInput]
    created_at: datetime


class TruckSummaryResponse(BaseModel):
    scenario_id: UUID
    active_truck_count: int
    active_truck_type_summary: list[TruckTypeSummary]


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str


class MessageResponse(BaseModel):
    message: str


class ScenarioQueryResponse(BaseModel):
    items: list[ScenarioListItem]
    summary: ScenarioDashboardSummary


class MasterDataListResponse(BaseModel):
    items: list[dict[str, Any]]


class ScenarioSnapshot(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    dispatch_date: date
    depot_id: str
    depot_service_time_minutes: int = 0
    orders: list[OrderInput]
    available_trucks: list[TruckInput]
    optimization_config: OptimizationConfig


class ScenarioAnalysisExperimentResult(BaseModel):
    experiment_id: str
    title: str
    summary: str
    scenario_status: SolutionStatus
    solver_status: str
    assignment_found: bool
    total_unserved_orders: int
    total_cost: float = 0
    solver_runtime_seconds: float
    changed_assumptions: list[str] = Field(default_factory=list)


class ScenarioAnalysisProblematicOrder(BaseModel):
    order_id: str
    spbu_id: str
    priority: bool
    eta: str | None = None
    heuristic_score: float
    experimental_score: float
    total_score: float
    reasons: list[str] = Field(default_factory=list)


class ScenarioAnalysisReport(BaseModel):
    root_cause_summary: str
    solver_status_explained: str
    key_findings: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    problematic_orders: list[ScenarioAnalysisProblematicOrder] = Field(default_factory=list)
    experiment_results: list[ScenarioAnalysisExperimentResult] = Field(default_factory=list)


class ScenarioAnalysisCreateRequest(BaseModel):
    level: AnalysisLevel


class ScenarioAnalysisJobResponse(BaseModel):
    analysis_id: UUID
    scenario_id: UUID
    level: AnalysisLevel
    status: AnalysisStatus
    message: str
    created_at: datetime


class ScenarioAnalysisListItem(BaseModel):
    analysis_id: UUID
    scenario_id: UUID
    level: AnalysisLevel
    status: AnalysisStatus
    message: str
    created_at: datetime
    updated_at: datetime


class ScenarioAnalysisQueryResponse(BaseModel):
    items: list[ScenarioAnalysisListItem]


class ScenarioAnalysisOverviewItem(BaseModel):
    analysis_id: UUID
    scenario_id: UUID
    dispatch_date: date
    depot_id: str
    scenario_status: SolutionStatus
    level: AnalysisLevel
    status: AnalysisStatus
    message: str
    created_at: datetime
    updated_at: datetime


class ScenarioAnalysisOverviewResponse(BaseModel):
    items: list[ScenarioAnalysisOverviewItem]


class ScenarioAnalysisDetailResponse(BaseModel):
    analysis_id: UUID
    scenario_id: UUID
    level: AnalysisLevel
    status: AnalysisStatus
    message: str
    report: ScenarioAnalysisReport | None = None
    created_at: datetime
    updated_at: datetime
