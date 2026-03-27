"""Add compartment payload to scenario trucks."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260326_0005"
down_revision = "20260318_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenario_trucks",
        sa.Column("compartments", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("scenario_trucks", "compartments", server_default=None)


def downgrade() -> None:
    op.drop_column("scenario_trucks", "compartments")
