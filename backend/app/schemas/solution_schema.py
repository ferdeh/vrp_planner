"""Solution orchestration schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.solver_setting_schema import SolverSettings


SolverProgressStep = Literal[
    "Building VRP Model",
    "Generating SPBU Clusters",
    "Refining with OR-Tools",
    "Final Validation",
    "Completed",
]


class InitialSolutionValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    route_count: int = 0
    assigned_shipments: int = 0


class FinalSolutionValidationResult(BaseModel):
    is_valid: bool
    status: str
    hard_constraint_violations: dict[str, list[Any]] = Field(default_factory=dict)
    soft_constraint_penalties: dict[str, float] = Field(default_factory=dict)


class SolverJobResponse(BaseModel):
    scenario_id: UUID
    status: str
    message: str
    created_at: datetime
    solver_mode: str
    solver_settings: SolverSettings
