"""yfinance data connector with caching and rate-limit awareness."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

from valuesentinel.logging_config import get_logger
from valuesentinel.models import FundamentalData, Ticker, TickerDataStatus

logger = get_logger("data.yfinance")

# ── Rate-limit tracking ───────────────────────────────

_daily_request_count: int = 0
_daily_reset: float = 0.0
YFINANCE_DAILY_LIMIT = 2000


def _check_rate_limit() -> None:
    """Self-imposed rate limit to avoid IP bans."""
    global _daily_request_count, _daily_reset
    now = time.time()
    if now - _daily_reset > 86400:
        _daily_request_count = 0
        _daily_reset = now
    if _daily_request_count >= YFINANCE_DAILY_LIMIT:
        logger.warning("yfinance daily rate limit reached (%d). Skipping.", YFINANCE_DAILY_LIMIT)
        raise RateLimitExceeded(f"yfinance daily limit of {YFINANCE_DAILY_LIMIT} reached")
    _daily_request_count += 1


class RateLimitExceeded(Exception):
    pass


class YFinanceDataError(Exception):
    pass


# ── Ticker info fetch ─────────────────────────────────


def fetch_ticker_info(symbol: str) -> dict[str, Any]:
    """Fetch basic ticker info (name, exchange, currency, sector, etc.)."""
    _check_rate_limit()
    try:
        tk = yf.Ticker(symbol)
        info = tk.info or {}
        return {
            "name": info.get("longName") or info.get("shortName", ""),
            "exchange": info.get("exchange", ""),
            "currency": info.get("currency", ""),
            "sector": info.get("sector", ""),
            "is_reit": "reit" in info.get("quoteType", "").lower()
            or "reit" in info.get("sector", "").lower()
            or "real estate" in info.get("industry", "").lower(),
            "forward_eps": info.get("forwardEps"),
            "trailing_eps": info.get("trailingEps"),
            "book_value": info.get("bookValue"),
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "total_debt": info.get("totalDebt"),
            "total_cash": info.get("totalCash"),
            "revenue_per_share": info.get("revenuePerShare"),
        }
    except Exception as e:
        logger.error("Failed to fetch info for %s: %s", symbol, e)
        raise YFinanceDataError(f"Cannot fetch info for {symbol}") from e


def fetch_live_price(symbol: str) -> float | None:
    """Fetch current/delayed price for a ticker."""
    _check_rate_limit()
    try:
        tk = yf.Ticker(symbol)
        # Try fast_info first, fall back to history
        price = getattr(tk, "fast_info", {}).get("lastPrice")
        if price is None:
            hist = tk.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        return float(price) if price is not None else None
    except Exception as e:
        logger.error("Failed to fetch price for %s: %s", symbol, e)
        return None


# ── Fundamental data fetch ────────────────────────────


def fetch_fundamentals(symbol: str) -> dict[str, Any]:
    """Fetch financial statements and derive fundamental data points.

    Returns a dict with lists of period data keyed by period_end date.
    """
    _check_rate_limit()
    try:
        tk = yf.Ticker(symbol)
        info = tk.info or {}
        result: dict[str, Any] = {
            "info": info,
            "periods": [],
        }

        # Quarterly financials
        inc_q = tk.quarterly_financials
        bs_q = tk.quarterly_balance_sheet
        cf_q = tk.quarterly_cashflow

        # Annual financials (fallback for intl companies reporting annually)
        inc_a = tk.financials
        bs_a = tk.balance_sheet
        cf_a = tk.cashflow

        # Process quarterly data
        if inc_q is not None and not inc_q.empty:
            result["periods"].extend(
                _extract_periods(inc_q, bs_q, cf_q, "quarterly", info)
            )

        # Process annual data
        if inc_a is not None and not inc_a.empty:
            result["periods"].extend(
                _extract_periods(inc_a, bs_a, cf_a, "annual", info)
            )

        # TTM (trailing twelve months) from info
        ttm = _extract_ttm_from_info(info)
        if ttm:
            result["periods"].append(ttm)

        return result

    except Exception as e:
        logger.error("Failed to fetch fundamentals for %s: %s", symbol, e)
        raise YFinanceDataError(f"Cannot fetch fundamentals for {symbol}") from e


def _safe_get(df: pd.DataFrame | None, row: str, col: Any) -> float | None:
    """Safely extract a value from a DataFrame."""
    if df is None or df.empty:
        return None
    try:
        if row in df.index and col in df.columns:
            val = df.loc[row, col]
            if pd.notna(val):
                return float(val)
    except (KeyError, TypeError, ValueError):
        pass
    return None


def _extract_periods(
    income: pd.DataFrame | None,
    balance: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    period_type: str,
    info: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract period-by-period fundamental data from financial statement DataFrames."""
    periods = []
    if income is None or income.empty:
        return periods

    for col in income.columns:
        period_end = col
        if isinstance(period_end, pd.Timestamp):
            period_end = period_end.to_pydatetime().replace(tzinfo=timezone.utc)

        # Income statement fields
        revenue = _safe_get(income, "Total Revenue", col)
        net_income = _safe_get(income, "Net Income", col)
        ebitda = _safe_get(income, "EBITDA", col)
        ebit = _safe_get(income, "EBIT", col) or _safe_get(income, "Operating Income", col)
        da = _safe_get(income, "Depreciation And Amortization In Income Statement", col)

        # Balance sheet fields
        total_debt = _safe_get(balance, "Total Debt", col)
        cash = (
            _safe_get(balance, "Cash And Cash Equivalents", col)
            or _safe_get(balance, "Cash Cash Equivalents And Short Term Investments", col)
        )
        preferred = _safe_get(balance, "Preferred Stock", col)
        minority = _safe_get(balance, "Minority Interest", col)
        shares = _safe_get(balance, "Ordinary Shares Number", col) or _safe_get(
            balance, "Share Issued", col
        )

        # Cash flow fields
        fcf = _safe_get(cashflow, "Free Cash Flow", col)
        capex = _safe_get(cashflow, "Capital Expenditure", col)

        # Per-share calculations
        eps_trailing = None
        book_value_ps = None
        revenue_ps = None
        if shares and shares > 0:
            if net_income is not None:
                eps_trailing = net_income / shares
            bv = _safe_get(balance, "Stockholders Equity", col) or _safe_get(
                balance, "Total Equity Gross Minority Interest", col
            )
            if bv is not None:
                book_value_ps = bv / shares
            if revenue is not None:
                revenue_ps = revenue / shares

        # REIT: FFO calculation
        ffo = None
        affo = None
        if da is not None and net_income is not None:
            gains = _safe_get(income, "Gain On Sale Of Security", col) or 0.0
            ffo = net_income + (da if da > 0 else -da) - gains
            if capex is not None:
                affo = ffo - abs(capex)

        periods.append({
            "period_end": period_end,
            "period_type": period_type,
            "revenue": revenue,
            "net_income": net_income,
            "ebitda": ebitda,
            "ebit": ebit,
            "eps_trailing": eps_trailing,
            "book_value_per_share": book_value_ps,
            "revenue_per_share": revenue_ps,
            "total_debt": total_debt,
            "cash_and_equivalents": cash,
            "preferred_equity": preferred,
            "minority_interest": minority,
            "shares_outstanding": shares,
            "free_cash_flow": fcf,
            "ffo": ffo,
            "affo": affo,
            "depreciation_amortization": da,
            "gains_on_asset_sales": _safe_get(income, "Gain On Sale Of Security", col),
            "recurring_capex": abs(capex) if capex is not None else None,
        })

    return periods


def _extract_ttm_from_info(info: dict[str, Any]) -> dict[str, Any] | None:
    """Build a TTM (trailing twelve months) data point from yfinance info dict."""
    if not info:
        return None
    now = datetime.now(timezone.utc)
    return {
        "period_end": now,
        "period_type": "ttm",
        "revenue": info.get("totalRevenue"),
        "net_income": info.get("netIncomeToCommon"),
        "ebitda": info.get("ebitda"),
        "ebit": info.get("operatingMargins", None),  # not directly ebit
        "eps_trailing": info.get("trailingEps"),
        "eps_forward": info.get("forwardEps"),
        "book_value_per_share": info.get("bookValue"),
        "revenue_per_share": info.get("revenuePerShare"),
        "total_debt": info.get("totalDebt"),
        "cash_and_equivalents": info.get("totalCash"),
        "preferred_equity": None,
        "minority_interest": None,
        "shares_outstanding": info.get("sharesOutstanding"),
        "free_cash_flow": info.get("freeCashflow"),
        "ffo": None,
        "affo": None,
        "depreciation_amortization": None,
        "gains_on_asset_sales": None,
        "recurring_capex": None,
    }


# ── Database persistence ──────────────────────────────


def sync_ticker(session: Session, symbol: str) -> Ticker:
    """Ensure a ticker exists in the DB, create or update from yfinance."""
    ticker = session.query(Ticker).filter(Ticker.symbol == symbol).first()
    info = fetch_ticker_info(symbol)

    if ticker is None:
        ticker = Ticker(symbol=symbol)
        session.add(ticker)

    ticker.name = info.get("name", "")
    ticker.exchange = info.get("exchange", "")
    ticker.currency = info.get("currency", "")
    ticker.sector = info.get("sector", "")
    ticker.is_reit = info.get("is_reit", False)
    ticker.data_status = TickerDataStatus.OK

    session.flush()
    return ticker


def refresh_fundamentals(session: Session, ticker: Ticker) -> int:
    """Fetch and cache fundamental data for a ticker. Returns number of periods saved."""
    try:
        data = fetch_fundamentals(ticker.symbol)
    except YFinanceDataError:
        ticker.data_status = TickerDataStatus.UNAVAILABLE
        return 0

    saved = 0
    for period in data.get("periods", []):
        period_end = period["period_end"]
        period_type = period.get("period_type", "quarterly")

        # Upsert: check if we already have this period
        existing = (
            session.query(FundamentalData)
            .filter(
                FundamentalData.ticker_id == ticker.id,
                FundamentalData.period_end == period_end,
                FundamentalData.period_type == period_type,
            )
            .first()
        )

        if existing is None:
            fd = FundamentalData(ticker_id=ticker.id, period_end=period_end)
        else:
            fd = existing

        # Map all fields
        for field in [
            "period_type", "revenue", "net_income", "ebitda", "ebit",
            "eps_trailing", "eps_forward", "book_value_per_share",
            "revenue_per_share", "total_debt", "cash_and_equivalents",
            "preferred_equity", "minority_interest", "shares_outstanding",
            "free_cash_flow", "ffo", "affo", "depreciation_amortization",
            "gains_on_asset_sales", "recurring_capex",
        ]:
            val = period.get(field)
            if val is not None:
                setattr(fd, field, val)

        fd.fetched_at = datetime.now(timezone.utc)
        if existing is None:
            session.add(fd)
        saved += 1

    ticker.last_fundamental_refresh = datetime.now(timezone.utc)

    # Compute history_years_available
    oldest = (
        session.query(FundamentalData.period_end)
        .filter(FundamentalData.ticker_id == ticker.id)
        .order_by(FundamentalData.period_end.asc())
        .first()
    )
    if oldest and oldest[0]:
        delta = datetime.now(timezone.utc) - oldest[0].replace(tzinfo=timezone.utc)
        ticker.history_years_available = round(delta.days / 365.25, 1)

    ticker.data_status = TickerDataStatus.OK
    logger.info("Refreshed %d periods for %s", saved, ticker.symbol)
    return saved


def get_historical_prices(symbol: str, years: int = 10) -> pd.DataFrame:
    """Fetch historical daily closing prices (split-adjusted) for up to N years."""
    _check_rate_limit()
    try:
        tk = yf.Ticker(symbol)
        period = f"{years}y"
        hist = tk.history(period=period, auto_adjust=True)
        if hist.empty:
            # Fallback: try 5y, then max
            for fallback in ["5y", "max"]:
                hist = tk.history(period=fallback, auto_adjust=True)
                if not hist.empty:
                    break
        return hist
    except Exception as e:
        logger.error("Failed to fetch historical prices for %s: %s", symbol, e)
        return pd.DataFrame()
