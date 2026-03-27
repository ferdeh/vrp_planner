"""Repository for system settings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import db_models, schemas


class SettingsRepository:
    """CRUD operations for singleton-like settings row."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_active(self) -> db_models.SystemSettings:
        stmt = select(db_models.SystemSettings).where(db_models.SystemSettings.is_active.is_(True))
        instance = self.db.execute(stmt).scalar_one_or_none()
        if instance:
            return instance

        instance = db_models.SystemSettings(
            default_optimization_config=schemas.OptimizationConfig().model_dump(),
            ui_preferences={},
            is_active=True,
        )
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def update(self, payload: schemas.SystemSettingsPayload) -> db_models.SystemSettings:
        instance = self.get_active()
        instance.default_optimization_config = payload.default_optimization_config.model_dump()
        instance.ui_preferences = payload.ui_preferences
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

