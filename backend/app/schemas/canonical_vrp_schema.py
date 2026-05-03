"""Canonical VRP schema for RouteFinder service requests."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.routefinder_cluster_schema import Cluster


class CanonicalScenario(BaseModel):
    scenario_id: str
    planning_date: str
    depot_codes: list[str] = Field(default_factory=list)


class CanonicalNode(BaseModel):
    node_id: str
    node_code: str
    node_name: str
    node_type: str
    lat: float | None = None
    lng: float | None = None
    truck_category: int | None = None
    time_window_start: str | None = None
    time_window_end: str | None = None
    supply_depot_ids: list[str] = Field(default_factory=list)
    cluster_id: str | None = None


class CanonicalVehicle(BaseModel):
    vehicle_id: str
    depot_id: str
    end_depot_id: str
    truck_category: int | None = None
    truck_type: str
    capacity_kl: float
    compartments: list[dict[str, Any]] = Field(default_factory=list)
    compatible_product_codes: list[str] = Field(default_factory=list)
    max_working_minutes: int | None = None
    max_trips: int | None = None
    shift_start: str | None = None
    shift_end: str | None = None
    is_available: bool = True


class CanonicalOrder(BaseModel):
    order_id: str
    parent_order_id: str
    node_id: str
    product_code: str
    quantity_kl: float
    service_time_minutes: int
    time_window_start: str | None = None
    time_window_end: str | None = None
    priority: bool = False
    eta: str | None = None
    allowed_truck_categories: list[int] = Field(default_factory=list)
    supply_depot_compatibility: list[str] = Field(default_factory=list)


class CanonicalMatrices(BaseModel):
    distance_matrix: list[list[int]] = Field(default_factory=list)
    duration_matrix: list[list[int]] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)


class CanonicalConstraints(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    max_working_minutes: int | None = None
    max_trips: int | None = None
    allow_split_delivery: bool = False


class CanonicalSettings(BaseModel):
    solver_backbone: str = "ortools"
    use_routefinder: bool = False
    cluster_mode: str = "soft"
    max_cluster_size: int = 5


class CanonicalVRPModel(BaseModel):
    scenario: CanonicalScenario
    nodes: list[CanonicalNode] = Field(default_factory=list)
    vehicles: list[CanonicalVehicle] = Field(default_factory=list)
    orders: list[CanonicalOrder] = Field(default_factory=list)
    clusters: list[Cluster] = Field(default_factory=list)
    matrices: CanonicalMatrices
    constraints: CanonicalConstraints
    settings: CanonicalSettings
