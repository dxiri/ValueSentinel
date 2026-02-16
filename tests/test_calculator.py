"""Tests for the ValuationCalculator."""

from __future__ import annotations

import pytest

from valuesentinel.calculator.valuation import ValuationCalculator, MetricResult
from valuesentinel.models import MetricType, Ticker, FundamentalData


class TestValuationCalculator:
    """Validate metric formulas against known values."""

    def test_pe_trailing(self, session, sample_ticker, aapl_fundamentals):
        """P/E = Price / EPS. AAPL at $150, EPS 6.42 → P/E ≈ 23.36."""
        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_ticker, 150.0, MetricType.PE_TRAILING)
        assert result is not None
        assert result.value is not None
        assert abs(result.value - (150.0 / 6.42)) < 0.01
        assert result.currency == "USD"

    def test_pe_forward(self, session, sample_ticker, aapl_fundamentals):
        """Forward P/E = Price / Forward EPS. $150 / 7.10 ≈ 21.13."""
        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_ticker, 150.0, MetricType.PE_FORWARD)
        assert result is not None
        assert result.value is not None
        assert abs(result.value - (150.0 / 7.10)) < 0.01

    def test_pe_forward_unavailable(self, session, sample_ticker, aapl_fundamentals):
        """If forward EPS is None, result should note N/A."""
        # Remove forward EPS from all fundamentals
        for fd in aapl_fundamentals:
            fd.eps_forward = None
        session.flush()

        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_ticker, 150.0, MetricType.PE_FORWARD)
        assert result is not None
        assert result.value is None
        assert "N/A" in result.note

    def test_pb_ratio(self, session, sample_ticker, aapl_fundamentals):
        """P/B = Price / Book Value Per Share. $150 / 4.38 ≈ 34.25."""
        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_ticker, 150.0, MetricType.P_B)
        assert result is not None
        assert result.value is not None
        assert abs(result.value - (150.0 / 4.38)) < 0.01

    def test_ps_ratio(self, session, sample_ticker, aapl_fundamentals):
        """P/S = Price / Revenue Per Share. $150 / 24.85 ≈ 6.04."""
        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_ticker, 150.0, MetricType.P_S)
        assert result is not None
        assert result.value is not None
        assert abs(result.value - (150.0 / 24.85)) < 0.15

    def test_ev_ebitda(self, session, sample_ticker, aapl_fundamentals):
        """EV/EBITDA with simplified EV (no preferred/minority)."""
        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_ticker, 150.0, MetricType.EV_EBITDA)
        assert result is not None
        assert result.value is not None
        # EV = 150 * 15.408B + 108B - 30B ≈ 2,389.2B
        # EV/EBITDA = 2389.2B / 130B ≈ 18.38
        expected_ev = 150.0 * 15_408_000_000 + 108_000_000_000 - 30_000_000_000
        expected = expected_ev / 130_000_000_000
        assert abs(result.value - expected) < 0.5
        assert result.ev_simplified is True  # no preferred/minority data

    def test_p_fcf(self, session, sample_ticker, aapl_fundamentals):
        """P/FCF = Price / (FCF / Shares). $150 / (108B / 15.408B) ≈ 21.40."""
        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_ticker, 150.0, MetricType.P_FCF)
        assert result is not None
        assert result.value is not None
        fcf_ps = 108_000_000_000 / 15_408_000_000
        expected = 150.0 / fcf_ps
        assert abs(result.value - expected) < 0.1

    def test_reit_p_ffo(self, session, sample_reit, reit_fundamentals):
        """P/FFO for REIT. Price $55, FFO 3.2B, Shares 860M → FFO/sh ≈ 3.72 → P/FFO ≈ 14.78."""
        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_reit, 55.0, MetricType.P_FFO)
        assert result is not None
        assert result.value is not None
        ffo_ps = 3_200_000_000 / 860_000_000
        expected = 55.0 / ffo_ps
        assert abs(result.value - expected) < 0.1

    def test_reit_p_affo(self, session, sample_reit, reit_fundamentals):
        """P/AFFO for REIT."""
        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_reit, 55.0, MetricType.P_AFFO)
        assert result is not None
        assert result.value is not None
        affo_ps = 2_700_000_000 / 860_000_000
        expected = 55.0 / affo_ps
        assert abs(result.value - expected) < 0.1

    def test_compute_all_returns_snapshot(self, session, sample_ticker, aapl_fundamentals):
        """compute_all should return a TickerSnapshot with multiple metrics."""
        calc = ValuationCalculator(session)
        snapshot = calc.compute_all(sample_ticker, 150.0)
        assert snapshot.symbol == "AAPL"
        assert snapshot.currency == "USD"
        assert snapshot.price == 150.0
        # Should have at least P/E, P/B, P/S, EV/EBITDA, P/FCF
        assert len(snapshot.metrics) >= 5

    def test_no_fundamentals(self, session, sample_ticker):
        """No fundamental data → empty snapshot."""
        calc = ValuationCalculator(session)
        snapshot = calc.compute_all(sample_ticker, 150.0)
        assert len(snapshot.metrics) == 0

    def test_historical_range(self, session, sample_ticker, aapl_fundamentals):
        """Historical min/max should be populated from cached data."""
        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_ticker, 150.0, MetricType.PE_TRAILING)
        assert result is not None
        assert result.historical_min is not None
        assert result.historical_max is not None
        assert result.historical_min <= result.historical_max

    def test_international_ticker_currency(self, session, sample_intl_ticker):
        """Non-US ticker should return metrics in its local currency."""
        from datetime import datetime, timezone

        fd = FundamentalData(
            ticker_id=sample_intl_ticker.id,
            period_end=datetime(2025, 9, 30, tzinfo=timezone.utc),
            period_type="ttm",
            eps_trailing=2.50,
            book_value_per_share=15.0,
            shares_outstanding=3_800_000_000,
        )
        session.add(fd)
        session.flush()

        calc = ValuationCalculator(session)
        result = calc.compute_single(sample_intl_ticker, 28.50, MetricType.PE_TRAILING)
        assert result is not None
        assert result.currency == "GBP"
        assert result.value is not None
        assert abs(result.value - (28.50 / 2.50)) < 0.01
