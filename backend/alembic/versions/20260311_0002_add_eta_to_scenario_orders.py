"""Add ETA to scenario orders."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260311_0002"
down_revision = "20260311_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenario_orders", sa.Column("eta", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("scenario_orders", "eta")
