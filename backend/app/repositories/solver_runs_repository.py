"""Repository for solver run metrics."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import db_models


class SolverRunsRepository:
    """Persist high-level solver run metadata."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_run(
        self,
        *,
        scenario_id: str,
        solver_mode: str,
        routefinder_enabled: bool,
        status: str,
    ) -> db_models.VRPSolverRun:
        instance = db_models.VRPSolverRun(
            scenario_id=scenario_id,
            solver_mode=solver_mode,
            routefinder_enabled=routefinder_enabled,
            status=status,
        )
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def update_run(
        self,
        instance: db_models.VRPSolverRun,
        **updates,
    ) -> db_models.VRPSolverRun:
        for key, value in updates.items():
            setattr(instance, key, value)
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance
