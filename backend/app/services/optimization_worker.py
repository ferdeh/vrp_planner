"""Background worker for optimization jobs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from uuid import UUID

from app.core.config import get_settings
from app.core import database as database_module
from app.models import schemas
from app.services.optimization_service import OptimizationService

logger = logging.getLogger(__name__)


class OptimizationWorker:
    """Execute optimization jobs outside the request cycle."""

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="optimization-worker")

    def submit(self, scenario_id: UUID | str, payload: schemas.OptimizationRequest) -> None:
        if get_settings().app_env.lower() == "test":
            self._run_job(str(scenario_id), payload.model_dump(mode="json"))
            return
        self.executor.submit(self._run_job, str(scenario_id), payload.model_dump(mode="json"))

    def _run_job(self, scenario_id: str, payload_data: dict) -> None:
        db = database_module.SessionLocal()
        try:
            payload = schemas.OptimizationRequest.model_validate(payload_data)
            OptimizationService(db).process_job(scenario_id, payload)
        except Exception:
            logger.exception("Background optimization failed for scenario %s", scenario_id)
        finally:
            db.close()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)


optimization_worker = OptimizationWorker()
