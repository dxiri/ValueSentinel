"""Widen enum string columns to accommodate full enum value names.

Revision ID: 002
Revises: 001
Create Date: 2026-02-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: str = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # alerts.metric: e.g. "PE_TRAILING" (11), "EV_EBITDA" (9) — widen to 30
    op.alter_column("alerts", "metric", type_=sa.String(30), existing_type=sa.String(20))
    # alerts.cooldown: e.g. "TWENTY_FOUR_HOURS" (17) — widen to 30
    op.alter_column("alerts", "cooldown", type_=sa.String(30), existing_type=sa.String(10))


def downgrade() -> None:
    op.alter_column("alerts", "metric", type_=sa.String(20), existing_type=sa.String(30))
    op.alter_column("alerts", "cooldown", type_=sa.String(10), existing_type=sa.String(30))
