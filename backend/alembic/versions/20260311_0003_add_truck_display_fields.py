"""Add truck display fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260311_0003"
down_revision = "20260311_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenario_trucks", sa.Column("no_polisi", sa.String(length=64), nullable=True))
    op.add_column("scenario_trucks", sa.Column("status", sa.String(length=32), nullable=True))
    op.add_column("scenario_trucks", sa.Column("not_available_from", sa.String(length=32), nullable=True))
    op.add_column("scenario_trucks", sa.Column("not_available_to", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("scenario_trucks", "not_available_to")
    op.drop_column("scenario_trucks", "not_available_from")
    op.drop_column("scenario_trucks", "status")
    op.drop_column("scenario_trucks", "no_polisi")
