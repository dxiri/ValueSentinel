"""SQLAlchemy ORM models for ValueSentinel."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


# ── Enums ──────────────────────────────────────────────


class MetricType(str, enum.Enum):
    PE_TRAILING = "pe_trailing"
    PE_FORWARD = "pe_forward"
    EV_EBITDA = "ev_ebitda"
    EV_EBIT = "ev_ebit"
    P_FCF = "p_fcf"
    P_FFO = "p_ffo"
    P_AFFO = "p_affo"
    P_B = "p_b"
    P_S = "p_s"


METRIC_DISPLAY_NAMES: dict[MetricType, str] = {
    MetricType.PE_TRAILING: "P/E (Trailing)",
    MetricType.PE_FORWARD: "P/E (Forward)",
    MetricType.EV_EBITDA: "EV/EBITDA",
    MetricType.EV_EBIT: "EV/EBIT",
    MetricType.P_FCF: "P/FCF",
    MetricType.P_FFO: "P/FFO",
    MetricType.P_AFFO: "P/AFFO",
    MetricType.P_B: "P/B",
    MetricType.P_S: "P/S",
}


class ConditionType(str, enum.Enum):
    ABSOLUTE_BELOW = "absolute_below"  # metric < X
    ABSOLUTE_ABOVE = "absolute_above"  # metric > X
    PERCENTAGE_DROP = "percentage_drop"  # metric drops Z% from baseline
    PERCENTAGE_RISE = "percentage_rise"  # metric rises Z% from baseline
    HISTORICAL_LOW = "historical_low"  # rolling window low
    HISTORICAL_HIGH = "historical_high"  # rolling window high


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    PAUSED = "paused"
    STOPPED = "stopped"
    ACKNOWLEDGED = "acknowledged"


class AlertPriority(str, enum.Enum):
    CRITICAL = "critical"
    NORMAL = "normal"
    INFORMATIONAL = "informational"


class CooldownPeriod(str, enum.Enum):
    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    TWELVE_HOURS = "12h"
    TWENTY_FOUR_HOURS = "24h"
    FORTY_EIGHT_HOURS = "48h"
    ONE_WEEK = "1w"


COOLDOWN_SECONDS: dict[CooldownPeriod, int] = {
    CooldownPeriod.ONE_HOUR: 3600,
    CooldownPeriod.SIX_HOURS: 21600,
    CooldownPeriod.TWELVE_HOURS: 43200,
    CooldownPeriod.TWENTY_FOUR_HOURS: 86400,
    CooldownPeriod.FORTY_EIGHT_HOURS: 172800,
    CooldownPeriod.ONE_WEEK: 604800,
}


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class TickerDataStatus(str, enum.Enum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


# ── Models ─────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Ticker(Base):
    """A watched ticker symbol."""

    __tablename__ = "tickers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=True)
    exchange = Column(String(50), nullable=True)
    currency = Column(String(10), nullable=True)
    sector = Column(String(100), nullable=True)
    is_reit = Column(Boolean, default=False)
    data_status = Column(
        Enum(TickerDataStatus), default=TickerDataStatus.OK, nullable=False
    )
    last_fundamental_refresh = Column(DateTime(timezone=True), nullable=True)
    history_years_available = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    fundamentals = relationship("FundamentalData", back_populates="ticker", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="ticker", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Ticker {self.symbol}>"


class FundamentalData(Base):
    """Cached quarterly/annual fundamental data for a ticker."""

    __tablename__ = "fundamental_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    period_type = Column(String(20), nullable=True)  # quarterly, annual, ttm

    # Income Statement
    revenue = Column(Float, nullable=True)
    net_income = Column(Float, nullable=True)
    ebitda = Column(Float, nullable=True)
    ebit = Column(Float, nullable=True)

    # Per-share
    eps_trailing = Column(Float, nullable=True)
    eps_forward = Column(Float, nullable=True)
    book_value_per_share = Column(Float, nullable=True)
    revenue_per_share = Column(Float, nullable=True)

    # Balance Sheet
    total_debt = Column(Float, nullable=True)
    cash_and_equivalents = Column(Float, nullable=True)
    preferred_equity = Column(Float, nullable=True)
    minority_interest = Column(Float, nullable=True)
    shares_outstanding = Column(Float, nullable=True)

    # Cash Flow
    free_cash_flow = Column(Float, nullable=True)

    # REIT Specifics
    ffo = Column(Float, nullable=True)
    affo = Column(Float, nullable=True)
    depreciation_amortization = Column(Float, nullable=True)
    gains_on_asset_sales = Column(Float, nullable=True)
    recurring_capex = Column(Float, nullable=True)

    fetched_at = Column(DateTime(timezone=True), default=_utcnow)

    ticker = relationship("Ticker", back_populates="fundamentals")

    __table_args__ = (
        UniqueConstraint("ticker_id", "period_end", "period_type", name="uq_fundamental_period"),
    )

    def __repr__(self) -> str:
        return f"<FundamentalData ticker_id={self.ticker_id} period={self.period_end}>"


class Alert(Base):
    """An alert definition created by the user."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False)
    metric = Column(Enum(MetricType), nullable=False)
    condition = Column(Enum(ConditionType), nullable=False)
    threshold_value = Column(Float, nullable=True)  # for absolute / percentage
    baseline_value = Column(Float, nullable=True)  # value at alert creation (for % change)
    priority = Column(Enum(AlertPriority), default=AlertPriority.NORMAL, nullable=False)
    cooldown = Column(Enum(CooldownPeriod), default=CooldownPeriod.TWENTY_FOUR_HOURS, nullable=False)
    status = Column(Enum(AlertStatus), default=AlertStatus.ACTIVE, nullable=False)

    # Notification channels
    notify_email = Column(Boolean, default=False)
    notify_telegram = Column(Boolean, default=True)
    notify_discord = Column(Boolean, default=False)
    notify_pushover = Column(Boolean, default=False)

    # Tracking
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    last_triggered_value = Column(Float, nullable=True)
    trigger_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    ticker = relationship("Ticker", back_populates="alerts")
    history = relationship("AlertHistory", back_populates="alert", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Alert {self.id} ticker_id={self.ticker_id} {self.metric.value} {self.condition.value}>"


class AlertHistory(Base):
    """Log of every alert trigger event."""

    __tablename__ = "alert_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    triggered_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    metric_value = Column(Float, nullable=False)
    threshold_value = Column(Float, nullable=True)
    historical_min = Column(Float, nullable=True)
    historical_max = Column(Float, nullable=True)
    timeframe_years = Column(Float, nullable=True)
    message = Column(Text, nullable=False)
    delivery_status = Column(Enum(DeliveryStatus), default=DeliveryStatus.PENDING, nullable=False)
    delivery_channels = Column(String(100), nullable=True)  # comma-separated
    ev_simplified = Column(Boolean, default=False)

    alert = relationship("Alert", back_populates="history")

    def __repr__(self) -> str:
        return f"<AlertHistory alert_id={self.alert_id} at {self.triggered_at}>"
