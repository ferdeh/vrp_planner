"""Version routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.models import schemas
from app.services.repository_version_service import get_repository_versions

router = APIRouter(prefix="/api/v1/version", tags=["version"])


@router.get("", response_model=schemas.RepositoryVersionResponse)
def get_version_route() -> schemas.RepositoryVersionResponse:
    """Return git version metadata for application repositories."""

    return get_repository_versions()
