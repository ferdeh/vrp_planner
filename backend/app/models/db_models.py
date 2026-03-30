"""ORM models for optimizer persistence."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Scenario(Base, TimestampMixin):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    dispatch_date: Mapped[date] = mapped_column(Date, nullable=False)
    depot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="error")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_request: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    orders: Mapped[list["ScenarioOrder"]] = relationship(back_populates="scenario", cascade="all, delete-orphan")
    trucks: Mapped[list["ScenarioTruck"]] = relationship(back_populates="scenario", cascade="all, delete-orphan")
    optimization_config: Mapped["OptimizationConfigDB"] = relationship(
        back_populates="scenario",
        uselist=False,
        cascade="all, delete-orphan",
    )
    result: Mapped["OptimizationResult"] = relationship(
        back_populates="scenario",
        uselist=False,
        cascade="all, delete-orphan",
    )
    diagnostics: Mapped[list["ScenarioDiagnostic"]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by=lambda: desc(ScenarioDiagnostic.created_at),
    )


class ScenarioOrder(Base):
    __tablename__ = "scenario_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    spbu_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_type: Mapped[str] = mapped_column(String(64), nullable=False)
    demand_kl: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eta: Mapped[str | None] = mapped_column(String(8), nullable=True)
    service_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    time_window_start: Mapped[str] = mapped_column(String(8), nullable=False)
    time_window_end: Mapped[str] = mapped_column(String(8), nullable=False)

    scenario: Mapped[Scenario] = relationship(back_populates="orders")


class ScenarioTruck(Base):
    __tablename__ = "scenario_trucks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    truck_id: Mapped[str] = mapped_column(String(128), nullable=False)
    no_polisi: Mapped[str | None] = mapped_column(String(64), nullable=True)
    truck_type: Mapped[str] = mapped_column(String(64), nullable=False)
    truck_category: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_kl: Mapped[float] = mapped_column(Float, nullable=False)
    fixed_cost: Mapped[float] = mapped_column(Float, nullable=False)
    variable_cost_per_km: Mapped[float] = mapped_column(Float, nullable=False)
    variable_cost_per_minute: Mapped[float] = mapped_column(Float, nullable=False)
    start_depot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    end_depot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    shift_start: Mapped[str] = mapped_column(String(8), nullable=False)
    shift_end: Mapped[str] = mapped_column(String(8), nullable=False)
    compatible_product_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    compartments: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    not_available_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    not_available_to: Mapped[str | None] = mapped_column(String(32), nullable=True)

    scenario: Mapped[Scenario] = relationship(back_populates="trucks")


class OptimizationConfigDB(Base, TimestampMixin):
    __tablename__ = "optimization_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    config_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    scenario: Mapped[Scenario] = relationship(back_populates="optimization_config")


class OptimizationResult(Base, TimestampMixin):
    __tablename__ = "optimization_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_demand: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_delivered_demand: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_unserved_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_truck_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_distance: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_time: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    solver_runtime_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    preprocessing_notes: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    active_truck_type_summary: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)

    scenario: Mapped[Scenario] = relationship(back_populates="result")
    routes: Mapped[list["OptimizationRoute"]] = relationship(
        back_populates="result",
        cascade="all, delete-orphan",
    )
    unserved_orders: Mapped[list["UnservedOrder"]] = relationship(
        back_populates="result",
        cascade="all, delete-orphan",
    )


class OptimizationRoute(Base):
    __tablename__ = "optimization_routes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    optimization_result_id: Mapped[str] = mapped_column(
        ForeignKey("optimization_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    truck_id: Mapped[str] = mapped_column(String(128), nullable=False)
    origin_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    origin_etd: Mapped[str | None] = mapped_column(String(8), nullable=True)
    truck_type: Mapped[str] = mapped_column(String(64), nullable=False)
    capacity_kl: Mapped[float] = mapped_column(Float, nullable=False)
    total_load: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    utilization_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    route_distance: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    route_time: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    stop_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    result: Mapped[OptimizationResult] = relationship(back_populates="routes")
    stops: Mapped[list["OptimizationRouteStop"]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
    )


class OptimizationRouteStop(Base):
    __tablename__ = "optimization_route_stops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    optimization_route_id: Mapped[str] = mapped_column(
        ForeignKey("optimization_routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    spbu_id: Mapped[str] = mapped_column(String(64), nullable=False)
    eta: Mapped[str] = mapped_column(String(8), nullable=False)
    etd: Mapped[str] = mapped_column(String(8), nullable=False)
    delivered_volume: Mapped[float] = mapped_column(Float, nullable=False)
    arrival_status: Mapped[str] = mapped_column(String(32), nullable=False)

    route: Mapped[OptimizationRoute] = relationship(back_populates="stops")


class UnservedOrder(Base):
    __tablename__ = "unserved_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    optimization_result_id: Mapped[str] = mapped_column(
        ForeignKey("optimization_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    spbu_id: Mapped[str] = mapped_column(String(64), nullable=False)
    demand_kl: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    result: Mapped[OptimizationResult] = relationship(back_populates="unserved_orders")


class ScenarioDiagnostic(Base, TimestampMixin):
    __tablename__ = "scenario_diagnostics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    scenario: Mapped[Scenario] = relationship(back_populates="diagnostics")


class SystemSettings(Base, TimestampMixin):
    __tablename__ = "system_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_optimization_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ui_preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
