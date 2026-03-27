"""Initial schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260311_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("dispatch_date", sa.Date(), nullable=False),
        sa.Column("depot_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("raw_request", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_scenarios_depot_id", "scenarios", ["depot_id"])

    op.create_table(
        "system_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("default_optimization_config", sa.JSON(), nullable=False),
        sa.Column("ui_preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "scenario_orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("spbu_id", sa.String(length=64), nullable=False),
        sa.Column("product_type", sa.String(length=64), nullable=False),
        sa.Column("demand_kl", sa.Float(), nullable=False),
        sa.Column("service_time_minutes", sa.Integer(), nullable=False),
        sa.Column("time_window_start", sa.String(length=8), nullable=False),
        sa.Column("time_window_end", sa.String(length=8), nullable=False),
    )
    op.create_index("ix_scenario_orders_scenario_id", "scenario_orders", ["scenario_id"])

    op.create_table(
        "scenario_trucks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("truck_id", sa.String(length=128), nullable=False),
        sa.Column("truck_type", sa.String(length=64), nullable=False),
        sa.Column("capacity_kl", sa.Float(), nullable=False),
        sa.Column("fixed_cost", sa.Float(), nullable=False),
        sa.Column("variable_cost_per_km", sa.Float(), nullable=False),
        sa.Column("variable_cost_per_minute", sa.Float(), nullable=False),
        sa.Column("start_depot_id", sa.String(length=64), nullable=False),
        sa.Column("end_depot_id", sa.String(length=64), nullable=False),
        sa.Column("shift_start", sa.String(length=8), nullable=False),
        sa.Column("shift_end", sa.String(length=8), nullable=False),
        sa.Column("compatible_product_types", sa.JSON(), nullable=False),
    )
    op.create_index("ix_scenario_trucks_scenario_id", "scenario_trucks", ["scenario_id"])

    op.create_table(
        "optimization_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_optimization_configs_scenario_id", "optimization_configs", ["scenario_id"], unique=True)

    op.create_table(
        "optimization_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("total_orders", sa.Integer(), nullable=False),
        sa.Column("total_demand", sa.Float(), nullable=False),
        sa.Column("total_delivered_demand", sa.Float(), nullable=False),
        sa.Column("total_unserved_orders", sa.Integer(), nullable=False),
        sa.Column("active_truck_count", sa.Integer(), nullable=False),
        sa.Column("total_distance", sa.Float(), nullable=False),
        sa.Column("total_time", sa.Float(), nullable=False),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("solver_runtime_seconds", sa.Float(), nullable=False),
        sa.Column("preprocessing_notes", sa.JSON(), nullable=False),
        sa.Column("active_truck_type_summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_optimization_results_scenario_id", "optimization_results", ["scenario_id"], unique=True)

    op.create_table(
        "optimization_routes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "optimization_result_id",
            sa.String(length=36),
            sa.ForeignKey("optimization_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("truck_id", sa.String(length=128), nullable=False),
        sa.Column("truck_type", sa.String(length=64), nullable=False),
        sa.Column("capacity_kl", sa.Float(), nullable=False),
        sa.Column("total_load", sa.Float(), nullable=False),
        sa.Column("utilization_percent", sa.Float(), nullable=False),
        sa.Column("route_distance", sa.Float(), nullable=False),
        sa.Column("route_time", sa.Float(), nullable=False),
        sa.Column("stop_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_optimization_routes_result_id", "optimization_routes", ["optimization_result_id"])

    op.create_table(
        "optimization_route_stops",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "optimization_route_id",
            sa.String(length=36),
            sa.ForeignKey("optimization_routes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("parent_order_id", sa.String(length=128), nullable=False),
        sa.Column("spbu_id", sa.String(length=64), nullable=False),
        sa.Column("eta", sa.String(length=8), nullable=False),
        sa.Column("etd", sa.String(length=8), nullable=False),
        sa.Column("delivered_volume", sa.Float(), nullable=False),
        sa.Column("arrival_status", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_optimization_route_stops_route_id", "optimization_route_stops", ["optimization_route_id"])

    op.create_table(
        "unserved_orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "optimization_result_id",
            sa.String(length=36),
            sa.ForeignKey("optimization_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("parent_order_id", sa.String(length=128), nullable=False),
        sa.Column("spbu_id", sa.String(length=64), nullable=False),
        sa.Column("demand_kl", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_unserved_orders_result_id", "unserved_orders", ["optimization_result_id"])


def downgrade() -> None:
    op.drop_index("ix_unserved_orders_result_id", table_name="unserved_orders")
    op.drop_table("unserved_orders")
    op.drop_index("ix_optimization_route_stops_route_id", table_name="optimization_route_stops")
    op.drop_table("optimization_route_stops")
    op.drop_index("ix_optimization_routes_result_id", table_name="optimization_routes")
    op.drop_table("optimization_routes")
    op.drop_index("ix_optimization_results_scenario_id", table_name="optimization_results")
    op.drop_table("optimization_results")
    op.drop_index("ix_optimization_configs_scenario_id", table_name="optimization_configs")
    op.drop_table("optimization_configs")
    op.drop_index("ix_scenario_trucks_scenario_id", table_name="scenario_trucks")
    op.drop_table("scenario_trucks")
    op.drop_index("ix_scenario_orders_scenario_id", table_name="scenario_orders")
    op.drop_table("scenario_orders")
    op.drop_table("system_settings")
    op.drop_index("ix_scenarios_depot_id", table_name="scenarios")
    op.drop_table("scenarios")
