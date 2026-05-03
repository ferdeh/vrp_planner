"""Add RouteFinder hybrid solver tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260430_0009"
down_revision = "20260328_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vrp_solver_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=True, unique=True),
        sa.Column("use_routefinder", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("routefinder_mode", sa.String(length=30), nullable=False, server_default="balanced"),
        sa.Column("routefinder_max_runtime_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("routefinder_candidate_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("use_historical_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback_to_ortools", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "vrp_solver_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
        sa.Column("solver_mode", sa.String(length=64), nullable=False),
        sa.Column("routefinder_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("initial_solution_score", sa.Float(), nullable=True),
        sa.Column("final_solution_score", sa.Float(), nullable=True),
        sa.Column("improvement_percent", sa.Float(), nullable=True),
        sa.Column("runtime_seconds", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vrp_solver_runs_scenario_id", "vrp_solver_runs", ["scenario_id"])

    op.create_table(
        "vrp_routefinder_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("solver_run_id", sa.String(length=36), sa.ForeignKey("vrp_solver_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column("runtime_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("selected_candidate_index", sa.Integer(), nullable=True),
        sa.Column("initial_solution_score", sa.Float(), nullable=True),
        sa.Column("validation_status", sa.String(length=30), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vrp_routefinder_runs_solver_run_id", "vrp_routefinder_runs", ["solver_run_id"])

    op.create_table(
        "vrp_solution_validations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("solver_run_id", sa.String(length=36), sa.ForeignKey("vrp_solver_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("validation_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("hard_constraint_violations", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("soft_constraint_penalties", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vrp_solution_validations_solver_run_id", "vrp_solution_validations", ["solver_run_id"])


def downgrade() -> None:
    op.drop_index("ix_vrp_solution_validations_solver_run_id", table_name="vrp_solution_validations")
    op.drop_table("vrp_solution_validations")
    op.drop_index("ix_vrp_routefinder_runs_solver_run_id", table_name="vrp_routefinder_runs")
    op.drop_table("vrp_routefinder_runs")
    op.drop_index("ix_vrp_solver_runs_scenario_id", table_name="vrp_solver_runs")
    op.drop_table("vrp_solver_runs")
    op.drop_table("vrp_solver_settings")
