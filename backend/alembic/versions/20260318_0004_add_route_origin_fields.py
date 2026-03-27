"""Add origin fields to optimization routes."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260318_0004"
down_revision = "20260311_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("optimization_routes", sa.Column("origin_name", sa.String(length=128), nullable=True))
    op.add_column("optimization_routes", sa.Column("origin_etd", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("optimization_routes", "origin_etd")
    op.drop_column("optimization_routes", "origin_name")
