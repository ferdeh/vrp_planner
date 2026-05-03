"""Repository for hybrid solver settings."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import db_models
from app.schemas.solver_setting_schema import SolverSettings


class SolverSettingsRepository:
    """CRUD helpers for RouteFinder hybrid settings."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def _build_default_row(self) -> db_models.VRPSolverSettings:
        defaults = SolverSettings(
            use_routefinder=self.settings.routefinder_default_enabled,
            cluster_mode=self.settings.routefinder_default_cluster_mode,
            max_cluster_size=self.settings.routefinder_default_max_cluster_size,
        )
        return db_models.VRPSolverSettings(
            id=str(uuid.uuid4()),
            tenant_id=None,
            use_routefinder=defaults.use_routefinder,
            cluster_mode=defaults.cluster_mode.value,
            max_cluster_size=defaults.max_cluster_size,
        )

    def get_active(self) -> db_models.VRPSolverSettings:
        stmt = select(db_models.VRPSolverSettings).where(db_models.VRPSolverSettings.tenant_id.is_(None))
        instance = self.db.execute(stmt).scalar_one_or_none()
        if instance is not None:
            return instance
        instance = self._build_default_row()
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def update(self, payload: SolverSettings) -> db_models.VRPSolverSettings:
        instance = self.get_active()
        instance.use_routefinder = payload.use_routefinder
        instance.cluster_mode = payload.cluster_mode.value
        instance.max_cluster_size = payload.max_cluster_size
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance
