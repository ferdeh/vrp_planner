"""Schemas for RouteFinder hybrid solver settings."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ClusterMode(str, Enum):
    SOFT = "soft"
    HARD = "hard"


class SolverSettings(BaseModel):
    use_routefinder: bool = False
    cluster_mode: ClusterMode = ClusterMode.SOFT
    max_cluster_size: int = Field(default=5, ge=3, le=6)


class SolverSettingsResponse(SolverSettings):
    id: UUID
    tenant_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
