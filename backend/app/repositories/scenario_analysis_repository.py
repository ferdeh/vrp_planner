"""Scenario analysis persistence helpers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.models import db_models, schemas


class ScenarioAnalysisRepository:
    """Repository for analysis job lifecycle and queries."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_analysis(self, scenario_id: UUID | str, level: schemas.AnalysisLevel) -> db_models.ScenarioDiagnostic:
        row = db_models.ScenarioDiagnostic(
            scenario_id=str(scenario_id),
            level=level,
            status="processing",
            message="Scenario analysis is in progress.",
            report_json={},
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_analysis(
        self,
        analysis_id: UUID | str,
        scenario_id: UUID | str | None = None,
    ) -> db_models.ScenarioDiagnostic | None:
        stmt = select(db_models.ScenarioDiagnostic).where(db_models.ScenarioDiagnostic.id == str(analysis_id))
        if scenario_id is not None:
            stmt = stmt.where(db_models.ScenarioDiagnostic.scenario_id == str(scenario_id))
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_scenario(self, scenario_id: UUID | str) -> schemas.ScenarioAnalysisQueryResponse:
        stmt = (
            select(db_models.ScenarioDiagnostic)
            .where(db_models.ScenarioDiagnostic.scenario_id == str(scenario_id))
            .order_by(desc(db_models.ScenarioDiagnostic.created_at))
        )
        rows = self.db.execute(stmt).scalars().all()
        return schemas.ScenarioAnalysisQueryResponse(
            items=[
                schemas.ScenarioAnalysisListItem(
                    analysis_id=UUID(row.id),
                    scenario_id=UUID(row.scenario_id),
                    level=row.level,
                    status=row.status,
                    message=row.message,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]
        )

    def list_all(self) -> schemas.ScenarioAnalysisOverviewResponse:
        stmt = (
            select(db_models.ScenarioDiagnostic)
            .options(
                joinedload(db_models.ScenarioDiagnostic.scenario).joinedload(db_models.Scenario.result),
            )
            .order_by(desc(db_models.ScenarioDiagnostic.created_at))
        )
        rows = self.db.execute(stmt).unique().scalars().all()
        return schemas.ScenarioAnalysisOverviewResponse(
            items=[
                schemas.ScenarioAnalysisOverviewItem(
                    analysis_id=UUID(row.id),
                    scenario_id=UUID(row.scenario_id),
                    dispatch_date=row.scenario.dispatch_date,
                    depot_id=row.scenario.depot_id,
                    scenario_status=(row.scenario.result.status if row.scenario.result else row.scenario.status),
                    level=row.level,
                    status=row.status,
                    message=row.message,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]
        )

    def save_completed(
        self,
        row: db_models.ScenarioDiagnostic,
        report: schemas.ScenarioAnalysisReport,
        message: str,
    ) -> db_models.ScenarioDiagnostic:
        row.status = "completed"
        row.message = message
        row.report_json = report.model_dump(mode="json")
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def save_error(self, row: db_models.ScenarioDiagnostic, message: str) -> db_models.ScenarioDiagnostic:
        row.status = "error"
        row.message = message
        row.report_json = {}
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
