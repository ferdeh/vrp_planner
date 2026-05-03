"""Client for the RouteFinder clustering service."""

from __future__ import annotations

import time

import httpx

from app.core.config import get_settings
from app.schemas.canonical_vrp_schema import CanonicalVRPModel
from app.schemas.routefinder_cluster_schema import ClusterResult
from app.services.routefinder_cluster_service import RouteFinderClusterService


class RouteFinderClient:
    """Call RouteFinder cluster service and normalize transport errors."""

    def __init__(
        self,
        *,
        service_url: str | None = None,
        http_client: httpx.Client | None = None,
        local_service: RouteFinderClusterService | None = None,
    ) -> None:
        settings = get_settings()
        self.service_url = (service_url or settings.routefinder_service_url).rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=settings.request_timeout_seconds)
        self.local_service = local_service or RouteFinderClusterService()

    def generate_clusters(
        self,
        canonical_model: CanonicalVRPModel,
        *,
        prefer_stub: bool = False,
    ) -> tuple[ClusterResult, float]:
        started = time.perf_counter()
        if prefer_stub or not self.service_url:
            response = self.local_service.generate(canonical_model)
            return response, time.perf_counter() - started

        try:
            http_response = self.http_client.post(
                f"{self.service_url}/routefinder/generate-clusters",
                json=canonical_model.model_dump(mode="json"),
            )
            http_response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ValueError("RouteFinder request timed out.") from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"RouteFinder request failed: {exc}") from exc

        return (
            ClusterResult.model_validate(http_response.json()),
            time.perf_counter() - started,
        )
