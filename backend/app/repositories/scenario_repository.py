"""Scenario persistence and query helpers."""

from __future__ import annotations

from statistics import mean
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.models import db_models, schemas


class ScenarioRepository:
    """Repository for scenario and summary access."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_scenario_snapshot(self, payload: schemas.OptimizationRequest) -> db_models.Scenario:
        scenario = db_models.Scenario(
            dispatch_date=payload.dispatch_date,
            depot_id=payload.depot_id,
            status="error",
            message="Scenario initialized.",
            raw_request=payload.model_dump(mode="json"),
            orders=[
                db_models.ScenarioOrder(**order.model_dump())
                for order in payload.orders
            ],
            trucks=[
                db_models.ScenarioTruck(**truck.model_dump())
                for truck in payload.available_trucks
            ],
            optimization_config=db_models.OptimizationConfigDB(
                config_snapshot=(
                    payload.optimization_config.model_dump() if payload.optimization_config else {}
                )
            ),
        )
        self.db.add(scenario)
        self.db.commit()
        self.db.refresh(scenario)
        return scenario

    def get_scenario(self, scenario_id: UUID | str) -> db_models.Scenario | None:
        stmt = (
            select(db_models.Scenario)
            .where(db_models.Scenario.id == str(scenario_id))
            .options(
                joinedload(db_models.Scenario.orders),
                joinedload(db_models.Scenario.trucks),
                joinedload(db_models.Scenario.optimization_config),
                joinedload(db_models.Scenario.result)
                .joinedload(db_models.OptimizationResult.routes)
                .joinedload(db_models.OptimizationRoute.stops),
                joinedload(db_models.Scenario.result).joinedload(db_models.OptimizationResult.unserved_orders),
            )
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def list_scenarios(self) -> schemas.ScenarioQueryResponse:
        stmt = (
            select(db_models.Scenario)
            .options(joinedload(db_models.Scenario.result))
            .order_by(desc(db_models.Scenario.created_at))
        )
        rows = self.db.execute(stmt).unique().scalars().all()
        items = [
            schemas.ScenarioListItem(
                scenario_id=UUID(row.id),
                dispatch_date=row.dispatch_date,
                depot_id=row.depot_id,
                status=row.result.status if row.result else row.status,
                active_truck_count=row.result.active_truck_count if row.result else 0,
                total_cost=row.result.total_cost if row.result else 0,
                total_distance=row.result.total_distance if row.result else 0,
                total_time=row.result.total_time if row.result else 0,
                created_at=row.created_at,
            )
            for row in rows
        ]
        feasible_counts = sum(1 for item in items if item.status in {"feasible", "partial"})
        average_active_trucks = mean([item.active_truck_count for item in items]) if items else 0.0
        return schemas.ScenarioQueryResponse(
            items=items,
            summary=schemas.ScenarioDashboardSummary(
                total_scenarios=len(items),
                feasible_scenarios=feasible_counts,
                average_active_trucks=round(average_active_trucks, 2),
            ),
        )

    def delete_scenarios(self, scenario_ids: list[UUID | str]) -> int:
        ids = [str(item) for item in scenario_ids]
        if not ids:
            return 0
        stmt = select(db_models.Scenario).where(db_models.Scenario.id.in_(ids))
        rows = self.db.execute(stmt).scalars().all()
        for row in rows:
            self.db.delete(row)
        self.db.commit()
        return len(rows)
