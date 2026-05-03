"""Internal RouteFinder service routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.canonical_vrp_schema import CanonicalVRPModel
from app.schemas.routefinder_cluster_schema import ClusterResult
from app.services.routefinder_cluster_service import RouteFinderClusterService

router = APIRouter(tags=["routefinder"])


@router.post("/routefinder/generate-clusters", response_model=ClusterResult)
def generate_clusters(payload: CanonicalVRPModel) -> ClusterResult:
    return RouteFinderClusterService().generate(payload)
