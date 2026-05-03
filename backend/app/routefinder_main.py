"""Entrypoint for the standalone RouteFinder stub service."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.routefinder import router as routefinder_router

app = FastAPI(title="vrp_routefinder_service")
app.include_router(health_router)
app.include_router(routefinder_router)
