"""Add priority flag to scenario orders."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260327_0007"
down_revision = "20260327_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenario_orders",
        sa.Column("priority", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("scenario_orders", "priority", server_default=None)


def downgrade() -> None:
    op.drop_column("scenario_orders", "priority")
