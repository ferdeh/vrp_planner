"""Add truck category to scenario trucks."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260327_0006"
down_revision = "20260326_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenario_trucks", sa.Column("truck_category", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenario_trucks", "truck_category")
