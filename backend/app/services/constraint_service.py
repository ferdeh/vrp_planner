"""Constraint merge and normalization service."""

from __future__ import annotations

from app.models import schemas


class ConstraintService:
    """Merge global defaults with request-level overrides."""

    def merge_config(
        self,
        settings_payload: schemas.SystemSettingsPayload,
        request_config: schemas.OptimizationConfig | None,
    ) -> schemas.OptimizationConfig:
        base = settings_payload.default_optimization_config.model_copy(deep=True)
        if request_config is None:
            return base
        merged = base.model_dump()
        override = request_config.model_dump(exclude_none=True)
        return schemas.OptimizationConfig.model_validate(self._deep_merge(merged, override))

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

