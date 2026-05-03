"""Repository for persisted RouteFinder cluster output."""

from __future__ import annotations

import uuid

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import db_models
from app.schemas.routefinder_cluster_schema import Cluster


class RouteFinderClustersRepository:
    """Persist cluster metadata per scenario."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def replace_for_scenario(
        self,
        scenario_id: str,
        clusters: list[Cluster],
    ) -> list[db_models.VRPCluster]:
        self.db.execute(
            delete(db_models.VRPCluster).where(db_models.VRPCluster.scenario_id == scenario_id)
        )
        instances = [
            db_models.VRPCluster(
                id=str(uuid.uuid4()),
                scenario_id=scenario_id,
                cluster_id=cluster.cluster_id,
                spbu_ids=list(cluster.spbu_ids),
                total_demand_kl=cluster.total_demand_kl,
            )
            for cluster in clusters
        ]
        self.db.add_all(instances)
        self.db.commit()
        for instance in instances:
            self.db.refresh(instance)
        return instances
