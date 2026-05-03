"""Repository for RouteFinder run attempts."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import db_models


class RouteFinderRunsRepository:
    """Persist RouteFinder request lifecycle details."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_run(
        self,
        *,
        solver_run_id: str | None,
        enabled: bool,
        status: str,
        cluster_mode: str,
        runtime_seconds: float,
        max_cluster_size: int,
    ) -> db_models.VRPRouteFinderRun:
        instance = db_models.VRPRouteFinderRun(
            solver_run_id=solver_run_id,
            enabled=enabled,
            status=status,
            cluster_mode=cluster_mode,
            runtime_seconds=runtime_seconds,
            max_cluster_size=max_cluster_size,
        )
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def update_run(
        self,
        instance: db_models.VRPRouteFinderRun,
        **updates,
    ) -> db_models.VRPRouteFinderRun:
        for key, value in updates.items():
            setattr(instance, key, value)
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance
