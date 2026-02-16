"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tickers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(30), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("exchange", sa.String(50), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("is_reit", sa.Boolean(), default=False),
        sa.Column("data_status", sa.String(20), default="ok", nullable=False),
        sa.Column("last_fundamental_refresh", sa.DateTime(timezone=True), nullable=True),
        sa.Column("history_years_available", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "fundamental_data",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker_id", sa.Integer(), sa.ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_type", sa.String(20), nullable=True),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("net_income", sa.Float(), nullable=True),
        sa.Column("ebitda", sa.Float(), nullable=True),
        sa.Column("ebit", sa.Float(), nullable=True),
        sa.Column("eps_trailing", sa.Float(), nullable=True),
        sa.Column("eps_forward", sa.Float(), nullable=True),
        sa.Column("book_value_per_share", sa.Float(), nullable=True),
        sa.Column("revenue_per_share", sa.Float(), nullable=True),
        sa.Column("total_debt", sa.Float(), nullable=True),
        sa.Column("cash_and_equivalents", sa.Float(), nullable=True),
        sa.Column("preferred_equity", sa.Float(), nullable=True),
        sa.Column("minority_interest", sa.Float(), nullable=True),
        sa.Column("shares_outstanding", sa.Float(), nullable=True),
        sa.Column("free_cash_flow", sa.Float(), nullable=True),
        sa.Column("ffo", sa.Float(), nullable=True),
        sa.Column("affo", sa.Float(), nullable=True),
        sa.Column("depreciation_amortization", sa.Float(), nullable=True),
        sa.Column("gains_on_asset_sales", sa.Float(), nullable=True),
        sa.Column("recurring_capex", sa.Float(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("ticker_id", "period_end", "period_type", name="uq_fundamental_period"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker_id", sa.Integer(), sa.ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric", sa.String(30), nullable=False),
        sa.Column("condition", sa.String(30), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("baseline_value", sa.Float(), nullable=True),
        sa.Column("priority", sa.String(20), default="normal", nullable=False),
        sa.Column("cooldown", sa.String(30), default="24h", nullable=False),
        sa.Column("status", sa.String(20), default="active", nullable=False),
        sa.Column("notify_email", sa.Boolean(), default=False),
        sa.Column("notify_telegram", sa.Boolean(), default=True),
        sa.Column("notify_discord", sa.Boolean(), default=False),
        sa.Column("notify_pushover", sa.Boolean(), default=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_triggered_value", sa.Float(), nullable=True),
        sa.Column("trigger_count", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "alert_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("historical_min", sa.Float(), nullable=True),
        sa.Column("historical_max", sa.Float(), nullable=True),
        sa.Column("timeframe_years", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(20), default="pending", nullable=False),
        sa.Column("delivery_channels", sa.String(100), nullable=True),
        sa.Column("ev_simplified", sa.Boolean(), default=False),
    )


def downgrade() -> None:
    op.drop_table("alert_history")
    op.drop_table("alerts")
    op.drop_table("fundamental_data")
    op.drop_table("tickers")
