"""Add notify_pushover column to alerts table.

Revision ID: 003
Revises: 002
Create Date: 2026-02-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: str = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("notify_pushover", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("alerts", "notify_pushover")
