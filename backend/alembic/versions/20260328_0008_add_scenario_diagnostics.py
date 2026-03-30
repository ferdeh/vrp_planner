"""Add scenario diagnostics table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260328_0008"
down_revision = "20260327_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_diagnostics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "scenario_id",
            sa.String(length=36),
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_scenario_diagnostics_scenario_id", "scenario_diagnostics", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_scenario_diagnostics_scenario_id", table_name="scenario_diagnostics")
    op.drop_table("scenario_diagnostics")
