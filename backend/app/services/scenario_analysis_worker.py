"""Background worker for scenario analysis jobs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from uuid import UUID

from app.core import database as database_module
from app.core.config import get_settings
from app.services.scenario_analysis_service import ScenarioAnalysisService

logger = logging.getLogger(__name__)


class ScenarioAnalysisWorker:
    """Execute scenario analysis jobs outside the request cycle."""

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="scenario-analysis-worker")

    def submit(self, analysis_id: UUID | str) -> None:
        if get_settings().app_env.lower() == "test":
            self._run_job(str(analysis_id))
            return
        self.executor.submit(self._run_job, str(analysis_id))

    def _run_job(self, analysis_id: str) -> None:
        db = database_module.SessionLocal()
        try:
            ScenarioAnalysisService(db).process_job(analysis_id)
        except Exception:
            logger.exception("Background scenario analysis failed for job %s", analysis_id)
        finally:
            db.close()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)


scenario_analysis_worker = ScenarioAnalysisWorker()
