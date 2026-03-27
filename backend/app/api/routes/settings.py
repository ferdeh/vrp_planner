"""Settings routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import schemas
from app.repositories.settings_repository import SettingsRepository

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("", response_model=schemas.SystemSettingsResponse)
def get_settings_route(db: Session = Depends(get_db)) -> schemas.SystemSettingsResponse:
    """Return active optimization settings."""

    instance = SettingsRepository(db).get_active()
    return schemas.SystemSettingsResponse(
        id=UUID(instance.id),
        default_optimization_config=schemas.OptimizationConfig.model_validate(
            instance.default_optimization_config
        ),
        ui_preferences=instance.ui_preferences,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


@router.put("", response_model=schemas.SystemSettingsResponse)
def update_settings_route(
    payload: schemas.SystemSettingsPayload,
    db: Session = Depends(get_db),
) -> schemas.SystemSettingsResponse:
    """Update active optimization settings."""

    instance = SettingsRepository(db).update(payload)
    return schemas.SystemSettingsResponse(
        id=UUID(instance.id),
        default_optimization_config=schemas.OptimizationConfig.model_validate(
            instance.default_optimization_config
        ),
        ui_preferences=instance.ui_preferences,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )

