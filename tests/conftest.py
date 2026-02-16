"""Shared test fixtures for ValueSentinel tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Force SQLite in-memory for tests
os.environ["DATABASE_URL"] = "sqlite://"

from valuesentinel.models import (
    Alert,
    AlertPriority,
    AlertStatus,
    Base,
    ConditionType,
    CooldownPeriod,
    FundamentalData,
    MetricType,
    Ticker,
    TickerDataStatus,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine) -> Session:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sess = factory()
    yield sess
    sess.close()


@pytest.fixture
def sample_ticker(session: Session) -> Ticker:
    """A US large-cap ticker with fundamental data."""
    ticker = Ticker(
        symbol="AAPL",
        name="Apple Inc.",
        exchange="NMS",
        currency="USD",
        sector="Technology",
        is_reit=False,
        data_status=TickerDataStatus.OK,
        history_years_available=10.0,
    )
    session.add(ticker)
    session.flush()
    return ticker


@pytest.fixture
def sample_reit(session: Session) -> Ticker:
    """A REIT ticker."""
    ticker = Ticker(
        symbol="O",
        name="Realty Income Corp",
        exchange="NMS",
        currency="USD",
        sector="Real Estate",
        is_reit=True,
        data_status=TickerDataStatus.OK,
        history_years_available=10.0,
    )
    session.add(ticker)
    session.flush()
    return ticker


@pytest.fixture
def sample_intl_ticker(session: Session) -> Ticker:
    """A non-US ticker (London)."""
    ticker = Ticker(
        symbol="SHEL.L",
        name="Shell plc",
        exchange="LSE",
        currency="GBP",
        sector="Energy",
        is_reit=False,
        data_status=TickerDataStatus.OK,
        history_years_available=8.5,
    )
    session.add(ticker)
    session.flush()
    return ticker


@pytest.fixture
def aapl_fundamentals(session: Session, sample_ticker: Ticker) -> list[FundamentalData]:
    """Sample fundamental data for AAPL — 4 quarters."""
    periods = []
    dates = [
        datetime(2025, 9, 30, tzinfo=timezone.utc),
        datetime(2025, 6, 30, tzinfo=timezone.utc),
        datetime(2025, 3, 31, tzinfo=timezone.utc),
        datetime(2024, 12, 31, tzinfo=timezone.utc),
    ]
    for i, d in enumerate(dates):
        fd = FundamentalData(
            ticker_id=sample_ticker.id,
            period_end=d,
            period_type="quarterly",
            revenue=94_836_000_000 + i * 1_000_000_000,
            net_income=24_160_000_000 + i * 500_000_000,
            ebitda=32_500_000_000,
            ebit=28_000_000_000,
            eps_trailing=6.42,
            eps_forward=7.10,
            book_value_per_share=4.38,
            revenue_per_share=6.15,
            total_debt=108_000_000_000,
            cash_and_equivalents=30_000_000_000,
            preferred_equity=None,
            minority_interest=None,
            shares_outstanding=15_408_000_000,
            free_cash_flow=27_000_000_000,
        )
        session.add(fd)
        periods.append(fd)

    # TTM summary
    ttm = FundamentalData(
        ticker_id=sample_ticker.id,
        period_end=datetime(2025, 12, 1, tzinfo=timezone.utc),
        period_type="ttm",
        revenue=383_000_000_000,
        net_income=97_000_000_000,
        ebitda=130_000_000_000,
        ebit=112_000_000_000,
        eps_trailing=6.42,
        eps_forward=7.10,
        book_value_per_share=4.38,
        revenue_per_share=24.85,
        total_debt=108_000_000_000,
        cash_and_equivalents=30_000_000_000,
        shares_outstanding=15_408_000_000,
        free_cash_flow=108_000_000_000,
    )
    session.add(ttm)
    periods.append(ttm)

    session.flush()
    return periods


@pytest.fixture
def reit_fundamentals(session: Session, sample_reit: Ticker) -> list[FundamentalData]:
    """Sample fundamental data for Realty Income."""
    fd = FundamentalData(
        ticker_id=sample_reit.id,
        period_end=datetime(2025, 9, 30, tzinfo=timezone.utc),
        period_type="ttm",
        revenue=4_000_000_000,
        net_income=870_000_000,
        ebitda=3_200_000_000,
        ebit=1_800_000_000,
        eps_trailing=1.01,
        book_value_per_share=28.50,
        revenue_per_share=4.65,
        total_debt=22_000_000_000,
        cash_and_equivalents=400_000_000,
        shares_outstanding=860_000_000,
        free_cash_flow=2_800_000_000,
        ffo=3_200_000_000,
        affo=2_700_000_000,
        depreciation_amortization=2_330_000_000,
    )
    session.add(fd)
    session.flush()
    return [fd]


@pytest.fixture
def sample_alert(session: Session, sample_ticker: Ticker) -> Alert:
    """An active absolute-below alert on P/E trailing."""
    alert = Alert(
        ticker_id=sample_ticker.id,
        metric=MetricType.PE_TRAILING,
        condition=ConditionType.ABSOLUTE_BELOW,
        threshold_value=25.0,
        priority=AlertPriority.NORMAL,
        cooldown=CooldownPeriod.TWENTY_FOUR_HOURS,
        status=AlertStatus.ACTIVE,
        notify_telegram=True,
    )
    session.add(alert)
    session.flush()
    return alert
