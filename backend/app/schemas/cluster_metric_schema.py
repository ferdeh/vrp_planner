"""Schemas for scenario cluster metrics dashboard."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ClusterMetricsSummary(BaseModel):
    total_distance: float
    total_trips: int
    cluster_adherence: float | None = None
    cross_cluster_moves: int
    shortage_kl: float
    truck_utilization: float | None = None
    total_clusters: int = 0
    total_spbu: int = 0


class ClusterMetricsCluster(BaseModel):
    cluster_id: str
    spbu_ids: list[str] = Field(default_factory=list)
    spbu_count: int
    total_demand_kl: float
    avg_distance: float
    cluster_leakage: float
    inbound_transitions: int
    outbound_transitions: int
    internal_transitions: int


class ClusterMetricsEdge(BaseModel):
    truck_id: str
    no_polisi: str | None = None
    from_spbu_id: str
    to_spbu_id: str
    from_cluster: str | None = None
    to_cluster: str | None = None
    distance_km: float
    trip_sequence: int
    is_cross_cluster: bool


class ClusterTruckMetric(BaseModel):
    truck_id: str
    no_polisi: str | None = None
    dominant_cluster: str | None = None
    purity_ratio: float
    cluster_count: int
    total_nodes: int
    dominant_cluster_nodes: int
    utilization_percent: float
    total_distance: float
    trip_count: int


class ClusterMetricsHistoryItem(BaseModel):
    scenario_id: UUID
    run_id: UUID | None = None
    created_at: datetime
    solver_mode: str
    total_distance: float
    total_demand: float
    total_trips: int
    cluster_adherence: float | None = None
    cross_cluster_moves: int


class ClusterMetricsResponse(BaseModel):
    scenario_id: UUID
    has_cluster_data: bool
    summary: ClusterMetricsSummary
    clusters: list[ClusterMetricsCluster] = Field(default_factory=list)
    edges: list[ClusterMetricsEdge] = Field(default_factory=list)
    truck_metrics: list[ClusterTruckMetric] = Field(default_factory=list)
    history: list[ClusterMetricsHistoryItem] = Field(default_factory=list)
