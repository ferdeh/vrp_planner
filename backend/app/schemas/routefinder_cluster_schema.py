"""Schemas for RouteFinder SPBU clustering."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Cluster(BaseModel):
    cluster_id: str
    spbu_ids: list[str] = Field(default_factory=list)
    total_demand_kl: float


class ClusterResult(BaseModel):
    clusters: list[Cluster] = Field(default_factory=list)
