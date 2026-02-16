"""Valuation metric calculator.

Implements all formulas from PRD §9.3 using cached fundamentals + live price.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from valuesentinel.data.yfinance_connector import fetch_ticker_info
from valuesentinel.logging_config import get_logger
from valuesentinel.models import FundamentalData, MetricType, Ticker

logger = get_logger("calculator")


@dataclass
class MetricResult:
    """Result of a single metric calculation."""

    metric: MetricType
    value: float | None
    currency: str
    timeframe_years: float
    historical_min: float | None
    historical_max: float | None
    ev_simplified: bool = False
    note: str = ""


@dataclass
class TickerSnapshot:
    """All calculable metrics for a ticker at a point in time."""

    symbol: str
    currency: str
    price: float
    timeframe_years: float
    metrics: dict[MetricType, MetricResult]


class ValuationCalculator:
    """Calculates valuation metrics using the 'Lazy Strategy':
    live price / cached fundamental value.
    """

    def __init__(self, session: Session):
        self.session = session

    def compute_all(
        self, ticker: Ticker, live_price: float
    ) -> TickerSnapshot:
        """Compute all applicable metrics for a ticker given a live price."""
        currency = ticker.currency or "USD"
        latest = self._get_latest_fundamental(ticker.id)
        if latest is None:
            logger.warning("No fundamental data for %s", ticker.symbol)
            return TickerSnapshot(
                symbol=ticker.symbol,
                currency=currency,
                price=live_price,
                timeframe_years=0.0,
                metrics={},
            )

        timeframe = ticker.history_years_available or 0.0
        info = self._get_info_fields(ticker)
        metrics: dict[MetricType, MetricResult] = {}

        # Market cap derived from price
        shares = latest.shares_outstanding or 0
        market_cap = live_price * shares if shares > 0 else None

        # ── P/E Trailing ──
        if latest.eps_trailing and latest.eps_trailing != 0:
            val = live_price / latest.eps_trailing
            h_min, h_max = self._historical_range(ticker.id, MetricType.PE_TRAILING, live_price)
            metrics[MetricType.PE_TRAILING] = MetricResult(
                MetricType.PE_TRAILING, val, currency, timeframe, h_min, h_max
            )

        # ── P/E Forward ──
        forward_eps = info.get("forward_eps") or latest.eps_forward
        if forward_eps and forward_eps != 0:
            val = live_price / forward_eps
            h_min, h_max = self._historical_range(ticker.id, MetricType.PE_FORWARD, live_price)
            metrics[MetricType.PE_FORWARD] = MetricResult(
                MetricType.PE_FORWARD, val, currency, timeframe, h_min, h_max
            )
        else:
            metrics[MetricType.PE_FORWARD] = MetricResult(
                MetricType.PE_FORWARD, None, currency, timeframe, None, None,
                note="N/A — No analyst estimates available",
            )

        # ── EV calculation ──
        ev, ev_simplified = self._compute_ev(market_cap, latest)

        # ── EV/EBITDA ──
        if ev is not None and latest.ebitda and latest.ebitda != 0:
            val = ev / latest.ebitda
            h_min, h_max = self._historical_range(ticker.id, MetricType.EV_EBITDA, live_price)
            metrics[MetricType.EV_EBITDA] = MetricResult(
                MetricType.EV_EBITDA, val, currency, timeframe, h_min, h_max,
                ev_simplified=ev_simplified,
            )

        # ── EV/EBIT ──
        if ev is not None and latest.ebit and latest.ebit != 0:
            val = ev / latest.ebit
            h_min, h_max = self._historical_range(ticker.id, MetricType.EV_EBIT, live_price)
            metrics[MetricType.EV_EBIT] = MetricResult(
                MetricType.EV_EBIT, val, currency, timeframe, h_min, h_max,
                ev_simplified=ev_simplified,
            )

        # ── P/FCF ──
        if latest.free_cash_flow and latest.free_cash_flow != 0 and shares > 0:
            fcf_ps = latest.free_cash_flow / shares
            val = live_price / fcf_ps
            h_min, h_max = self._historical_range(ticker.id, MetricType.P_FCF, live_price)
            metrics[MetricType.P_FCF] = MetricResult(
                MetricType.P_FCF, val, currency, timeframe, h_min, h_max
            )

        # ── P/B ──
        if latest.book_value_per_share and latest.book_value_per_share != 0:
            val = live_price / latest.book_value_per_share
            h_min, h_max = self._historical_range(ticker.id, MetricType.P_B, live_price)
            metrics[MetricType.P_B] = MetricResult(
                MetricType.P_B, val, currency, timeframe, h_min, h_max
            )

        # ── P/S ──
        if latest.revenue_per_share and latest.revenue_per_share != 0:
            val = live_price / latest.revenue_per_share
            h_min, h_max = self._historical_range(ticker.id, MetricType.P_S, live_price)
            metrics[MetricType.P_S] = MetricResult(
                MetricType.P_S, val, currency, timeframe, h_min, h_max
            )

        # ── P/FFO (REIT) ──
        if ticker.is_reit and latest.ffo and latest.ffo != 0 and shares > 0:
            ffo_ps = latest.ffo / shares
            val = live_price / ffo_ps
            h_min, h_max = self._historical_range(ticker.id, MetricType.P_FFO, live_price)
            metrics[MetricType.P_FFO] = MetricResult(
                MetricType.P_FFO, val, currency, timeframe, h_min, h_max
            )

        # ── P/AFFO (REIT) ──
        if ticker.is_reit and latest.affo and latest.affo != 0 and shares > 0:
            affo_ps = latest.affo / shares
            val = live_price / affo_ps
            h_min, h_max = self._historical_range(ticker.id, MetricType.P_AFFO, live_price)
            metrics[MetricType.P_AFFO] = MetricResult(
                MetricType.P_AFFO, val, currency, timeframe, h_min, h_max
            )

        return TickerSnapshot(
            symbol=ticker.symbol,
            currency=currency,
            price=live_price,
            timeframe_years=timeframe,
            metrics=metrics,
        )

    def compute_single(
        self, ticker: Ticker, live_price: float, metric: MetricType
    ) -> MetricResult | None:
        """Compute a single metric for alert checking."""
        snapshot = self.compute_all(ticker, live_price)
        return snapshot.metrics.get(metric)

    # ── Private helpers ───────────────────────────────

    def _get_latest_fundamental(self, ticker_id: int) -> FundamentalData | None:
        """Get the most recent fundamental data, preferring TTM > quarterly > annual."""
        for ptype in ["ttm", "quarterly", "annual"]:
            fd = (
                self.session.query(FundamentalData)
                .filter(
                    FundamentalData.ticker_id == ticker_id,
                    FundamentalData.period_type == ptype,
                )
                .order_by(FundamentalData.period_end.desc())
                .first()
            )
            if fd is not None:
                return fd
        return None

    def _get_info_fields(self, ticker: Ticker) -> dict:
        """Get supplementary info fields from the latest TTM or yfinance."""
        ttm = (
            self.session.query(FundamentalData)
            .filter(
                FundamentalData.ticker_id == ticker.id,
                FundamentalData.period_type == "ttm",
            )
            .order_by(FundamentalData.period_end.desc())
            .first()
        )
        return {
            "forward_eps": ttm.eps_forward if ttm else None,
        }

    def _compute_ev(
        self, market_cap: float | None, fd: FundamentalData
    ) -> tuple[float | None, bool]:
        """Compute Enterprise Value. Returns (ev, is_simplified)."""
        if market_cap is None:
            return None, False

        total_debt = fd.total_debt or 0
        cash = fd.cash_and_equivalents or 0
        preferred = fd.preferred_equity
        minority = fd.minority_interest

        if preferred is not None or minority is not None:
            # Full formula: MC + Debt + Preferred + Minority - Cash
            ev = market_cap + total_debt + (preferred or 0) + (minority or 0) - cash
            return ev, False
        else:
            # Simplified: MC + Debt - Cash
            ev = market_cap + total_debt - cash
            return ev, True

    def _historical_range(
        self,
        ticker_id: int,
        metric: MetricType,
        live_price: float,
        max_years: int = 10,
    ) -> tuple[float | None, float | None]:
        """Compute the historical min/max for a metric over the available window.

        Uses cached fundamentals across all periods to derive historical metric values.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_years * 365.25)

        fundamentals = (
            self.session.query(FundamentalData)
            .filter(
                FundamentalData.ticker_id == ticker_id,
                FundamentalData.period_end >= cutoff,
            )
            .order_by(FundamentalData.period_end.asc())
            .all()
        )

        if not fundamentals:
            return None, None

        values: list[float] = []
        for fd in fundamentals:
            val = self._metric_from_fundamental(fd, metric, live_price)
            if val is not None and val > 0:
                values.append(val)

        if not values:
            return None, None

        return min(values), max(values)

    def _metric_from_fundamental(
        self, fd: FundamentalData, metric: MetricType, price: float
    ) -> float | None:
        """Calculate a single metric value from a fundamental data row and price."""
        shares = fd.shares_outstanding or 0

        if metric == MetricType.PE_TRAILING:
            if fd.eps_trailing and fd.eps_trailing != 0:
                return price / fd.eps_trailing
        elif metric == MetricType.PE_FORWARD:
            if fd.eps_forward and fd.eps_forward != 0:
                return price / fd.eps_forward
        elif metric in (MetricType.EV_EBITDA, MetricType.EV_EBIT):
            if shares > 0:
                mc = price * shares
                ev = mc + (fd.total_debt or 0) + (fd.preferred_equity or 0) + (fd.minority_interest or 0) - (fd.cash_and_equivalents or 0)
                divisor = fd.ebitda if metric == MetricType.EV_EBITDA else fd.ebit
                if divisor and divisor != 0:
                    return ev / divisor
        elif metric == MetricType.P_FCF:
            if fd.free_cash_flow and fd.free_cash_flow != 0 and shares > 0:
                return price / (fd.free_cash_flow / shares)
        elif metric == MetricType.P_B:
            if fd.book_value_per_share and fd.book_value_per_share != 0:
                return price / fd.book_value_per_share
        elif metric == MetricType.P_S:
            if fd.revenue_per_share and fd.revenue_per_share != 0:
                return price / fd.revenue_per_share
        elif metric == MetricType.P_FFO:
            if fd.ffo and fd.ffo != 0 and shares > 0:
                return price / (fd.ffo / shares)
        elif metric == MetricType.P_AFFO:
            if fd.affo and fd.affo != 0 and shares > 0:
                return price / (fd.affo / shares)

        return None
