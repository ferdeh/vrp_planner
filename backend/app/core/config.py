"""Application configuration."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


DEFAULT_CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|"
    r"10\.\d+\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|"
    r"192\.168\.\d+\.\d+"
    r")(:\d+)?$"
)


class Settings(BaseModel):
    """Environment-backed application settings."""

    app_name: str = Field(default_factory=lambda: os.getenv("APP_NAME", "vrp_planner"))
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "dev"))
    app_host: str = Field(default_factory=lambda: os.getenv("APP_HOST", "0.0.0.0"))
    app_port: int = Field(default_factory=lambda: int(os.getenv("APP_PORT", "8080")))
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://planner:planner@planner-db:5432/vrp_planner",
        )
    )
    master_data_api_base_url: str = Field(
        default_factory=lambda: os.getenv(
            "MASTER_DATA_API_BASE_URL",
            "http://spbu-backend:8000",
        )
    )
    truck_master_data_api_base_url: str = Field(
        default_factory=lambda: os.getenv(
            "TRUCK_MASTER_DATA_API_BASE_URL",
            "http://truck-backend:8000",
        )
    )
    planner_public_base_url: str = Field(
        default_factory=lambda: os.getenv("PLANNER_PUBLIC_BASE_URL", "http://planner.localhost:8088")
    )
    planner_auth_logout_url: str = Field(
        default_factory=lambda: os.getenv(
            "PLANNER_AUTH_LOGOUT_URL",
            "http://auth.localhost:8088/realms/vrp-platform/protocol/openid-connect/logout",
        )
    )
    planner_oauth_client_id: str = Field(
        default_factory=lambda: os.getenv("PLANNER_OAUTH_CLIENT_ID", "oauth2-proxy-planner")
    )
    use_mock_master_data: bool = Field(default_factory=lambda: _get_bool("USE_MOCK_MASTER_DATA", False))
    solver_max_seconds: int = Field(default_factory=lambda: int(os.getenv("SOLVER_MAX_SECONDS", "30")))
    solver_first_strategy: str = Field(
        default_factory=lambda: os.getenv("SOLVER_FIRST_STRATEGY", "PATH_CHEAPEST_ARC")
    )
    solver_local_search: str = Field(
        default_factory=lambda: os.getenv("SOLVER_LOCAL_SEARCH", "GUIDED_LOCAL_SEARCH")
    )
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://planner.localhost:8088").split(",")
            if origin.strip()
        ]
    )
    cors_origin_regex: str | None = Field(
        default_factory=lambda: os.getenv("CORS_ORIGIN_REGEX") or DEFAULT_CORS_ORIGIN_REGEX
    )
    api_paths: dict[str, str] = Field(
        default_factory=lambda: {
            "spbu_list": os.getenv("MASTER_DATA_SPBU_PATH", "/api/spbu"),
            "spbu_detail": os.getenv("MASTER_DATA_SPBU_DETAIL_PATH", "/api/spbu/{id}"),
            "depots": os.getenv("MASTER_DATA_DEPOTS_PATH", "/api/depots"),
            "nodes": os.getenv("MASTER_DATA_NODES_PATH", "/nodes"),
            "trucks": os.getenv("TRUCK_MASTER_DATA_TRUCKS_PATH", "/api/trucks"),
            "time_matrix": os.getenv("NETWORK_TIME_MATRIX_PATH", "/api/network/time-matrix"),
            "distance_matrix": os.getenv("NETWORK_DISTANCE_MATRIX_PATH", "/api/network/distance-matrix"),
            "effective_edges": os.getenv("NETWORK_EFFECTIVE_EDGES_PATH", "/edges/effective"),
            "feasible_routes": os.getenv("ROUTES_FEASIBLE_PATH", "/api/routes/feasible"),
        }
    )
    request_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("EXTERNAL_API_TIMEOUT_SECONDS", "10"))
    )

    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() == "dev"

    @property
    def normalized_cors_origin_regex(self) -> str | None:
        if not self.cors_origin_regex:
            return None
        pattern = self.cors_origin_regex.strip()
        if not pattern:
            return None
        re.compile(pattern)
        return pattern

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return memoized settings instance."""

    return Settings()
