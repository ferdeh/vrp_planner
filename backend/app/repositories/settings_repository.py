"""Repository for system settings."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import db_models, schemas


_CURRENT_PENALTY_DEFAULTS = schemas.PenaltyConfig()
_LEGACY_PENALTY_DEFAULTS: dict[str, float] = {
    "unserved_order_penalty": 100000.0,
    "active_truck_idle_penalty_per_minute": 50.0,
    "unused_opportunity_capacity_penalty_per_kl": 500.0,
}


class SettingsRepository:
    """CRUD operations for singleton-like settings row."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _normalize_default_optimization_config(
        self,
        payload: Any,
    ) -> tuple[dict[str, Any], bool]:
        source = payload if isinstance(payload, dict) else {}
        penalties_source = source.get("penalties") if isinstance(source.get("penalties"), dict) else {}
        config = schemas.OptimizationConfig.model_validate(source)
        changed = not isinstance(payload, dict)

        if "active_truck_idle_threshold_percent_truck_count" not in penalties_source:
            config.penalties.active_truck_idle_threshold_percent_truck_count = (
                _CURRENT_PENALTY_DEFAULTS.active_truck_idle_threshold_percent_truck_count
            )
            changed = True
        if "active_truck_idle_threshold_percent_depot_operation" not in penalties_source:
            config.penalties.active_truck_idle_threshold_percent_depot_operation = (
                _CURRENT_PENALTY_DEFAULTS.active_truck_idle_threshold_percent_depot_operation
            )
            changed = True

        for field_name, legacy_default in _LEGACY_PENALTY_DEFAULTS.items():
            if field_name not in penalties_source:
                changed = True
                continue
            current_value = penalties_source.get(field_name)
            if current_value == legacy_default:
                setattr(config.penalties, field_name, getattr(_CURRENT_PENALTY_DEFAULTS, field_name))
                changed = True

        normalized = config.model_dump()
        if normalized != source:
            changed = True
        return normalized, changed

    def get_active(self) -> db_models.SystemSettings:
        stmt = select(db_models.SystemSettings).where(db_models.SystemSettings.is_active.is_(True))
        instance = self.db.execute(stmt).scalar_one_or_none()
        if instance:
            normalized_config, changed = self._normalize_default_optimization_config(
                instance.default_optimization_config
            )
            if changed:
                instance.default_optimization_config = normalized_config
                self.db.add(instance)
                self.db.commit()
                self.db.refresh(instance)
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
