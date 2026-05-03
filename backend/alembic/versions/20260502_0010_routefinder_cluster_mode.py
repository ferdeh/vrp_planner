"""Convert RouteFinder warm-start tables to cluster mode."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260502_0010"
down_revision = "20260430_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("vrp_solver_settings") as batch_op:
        batch_op.add_column(
            sa.Column("cluster_mode", sa.String(length=30), nullable=False, server_default="soft")
        )
        batch_op.add_column(
            sa.Column("max_cluster_size", sa.Integer(), nullable=False, server_default="5")
        )
        batch_op.drop_column("routefinder_mode")
        batch_op.drop_column("routefinder_max_runtime_seconds")
        batch_op.drop_column("routefinder_candidate_count")
        batch_op.drop_column("use_historical_seed")
        batch_op.drop_column("fallback_to_ortools")

    with op.batch_alter_table("vrp_routefinder_runs") as batch_op:
        batch_op.add_column(
            sa.Column("cluster_mode", sa.String(length=30), nullable=False, server_default="soft")
        )
        batch_op.add_column(
            sa.Column("max_cluster_size", sa.Integer(), nullable=False, server_default="5")
        )
        batch_op.add_column(
            sa.Column("cluster_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("total_clustered_demand_kl", sa.Numeric(), nullable=False, server_default="0")
        )
        batch_op.drop_column("mode")
        batch_op.drop_column("candidate_count")
        batch_op.drop_column("selected_candidate_index")
        batch_op.drop_column("initial_solution_score")
        batch_op.drop_column("validation_status")

    op.create_table(
        "vrp_clusters",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("spbu_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_demand_kl", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vrp_clusters_scenario_id", "vrp_clusters", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_vrp_clusters_scenario_id", table_name="vrp_clusters")
    op.drop_table("vrp_clusters")

    with op.batch_alter_table("vrp_routefinder_runs") as batch_op:
        batch_op.add_column(sa.Column("validation_status", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("initial_solution_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("selected_candidate_index", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="3")
        )
        batch_op.add_column(sa.Column("mode", sa.String(length=30), nullable=False, server_default="balanced"))
        batch_op.drop_column("total_clustered_demand_kl")
        batch_op.drop_column("cluster_count")
        batch_op.drop_column("max_cluster_size")
        batch_op.drop_column("cluster_mode")

    with op.batch_alter_table("vrp_solver_settings") as batch_op:
        batch_op.add_column(sa.Column("fallback_to_ortools", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("use_historical_seed", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(
            sa.Column("routefinder_candidate_count", sa.Integer(), nullable=False, server_default="3")
        )
        batch_op.add_column(
            sa.Column("routefinder_max_runtime_seconds", sa.Integer(), nullable=False, server_default="30")
        )
        batch_op.add_column(
            sa.Column("routefinder_mode", sa.String(length=30), nullable=False, server_default="balanced")
        )
        batch_op.drop_column("max_cluster_size")
        batch_op.drop_column("cluster_mode")
