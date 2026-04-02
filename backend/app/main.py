"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.master_data_proxy import router as master_data_router
from app.api.routes.optimization import router as optimization_router
from app.api.routes.scenarios import router as scenario_router
from app.api.routes.settings import router as settings_router
from app.core.config import get_settings
from app.core.database import Base, get_engine
from app.core.logging import configure_logging
from app.models import db_models  # noqa: F401
from app.services.optimization_worker import optimization_worker
from app.services.scenario_analysis_worker import scenario_analysis_worker

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize application resources on startup."""

    Base.metadata.create_all(bind=get_engine())
    logger.info("Application started in %s mode", settings.app_env)
    yield
    optimization_worker.shutdown()
    scenario_analysis_worker.shutdown()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.normalized_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    """Convert validation and domain errors to 400 responses."""

    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Convert unexpected errors to 500 responses."""

    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(optimization_router)
app.include_router(scenario_router)
app.include_router(master_data_router)
