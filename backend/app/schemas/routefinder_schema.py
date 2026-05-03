"""RouteFinder service request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.canonical_vrp_schema import CanonicalVRPModel


class RouteFinderGenerateRequest(CanonicalVRPModel):
    pass


class RouteFinderInitialRoute(BaseModel):
    vehicle_id: str
    node_sequence: list[str] = Field(default_factory=list)


class RouteFinderScore(BaseModel):
    estimated_distance: float = 0
    estimated_duration: float = 0
    estimated_utilization: float = 0


class RouteFinderGenerateResponse(BaseModel):
    status: str
    initial_routes: list[RouteFinderInitialRoute] = Field(default_factory=list)
    score: RouteFinderScore = Field(default_factory=RouteFinderScore)
    warnings: list[str] = Field(default_factory=list)
