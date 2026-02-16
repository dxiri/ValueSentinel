"""Tests for the alert engine — trigger conditions, cooldown, and state management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from valuesentinel.alerts.engine import AlertEngine
from valuesentinel.calculator.valuation import MetricResult
from valuesentinel.models import (
    Alert,
    AlertHistory,
    AlertPriority,
    AlertStatus,
    ConditionType,
    CooldownPeriod,
    DeliveryStatus,
    MetricType,
    TickerDataStatus,
)


class TestAlertConditions:
    """Test each of the three trigger condition types."""

    def test_absolute_below_triggers(self, session, sample_ticker, aapl_fundamentals, sample_alert):
        """P/E < 25 should trigger when P/E is 23.36 (price=$150, EPS=6.42)."""
        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 150.0

        triggered = engine.check_all()

        # 150/6.42 ≈ 23.36 < 25 → should trigger
        assert len(triggered) == 1
        assert triggered[0].metric_value == pytest.approx(150.0 / 6.42, abs=0.1)

    def test_absolute_below_no_trigger(self, session, sample_ticker, aapl_fundamentals, sample_alert):
        """P/E < 25 should NOT trigger when P/E is 30 (price=$192.6+)."""
        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 192.6  # 192.6 / 6.42 ≈ 30

        triggered = engine.check_all()
        assert len(triggered) == 0

    def test_absolute_above_triggers(self, session, sample_ticker, aapl_fundamentals):
        """P/E > 30 triggers when P/E is 35."""
        alert = Alert(
            ticker_id=sample_ticker.id,
            metric=MetricType.PE_TRAILING,
            condition=ConditionType.ABSOLUTE_ABOVE,
            threshold_value=30.0,
            priority=AlertPriority.NORMAL,
            cooldown=CooldownPeriod.TWENTY_FOUR_HOURS,
            status=AlertStatus.ACTIVE,
            notify_telegram=True,
        )
        session.add(alert)
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 224.7  # 224.7 / 6.42 ≈ 35

        triggered = engine.check_all()
        assert len(triggered) == 1

    def test_percentage_drop_triggers(self, session, sample_ticker, aapl_fundamentals):
        """Alert when P/E drops 10% from baseline 30."""
        alert = Alert(
            ticker_id=sample_ticker.id,
            metric=MetricType.PE_TRAILING,
            condition=ConditionType.PERCENTAGE_DROP,
            threshold_value=10.0,  # 10%
            baseline_value=30.0,
            priority=AlertPriority.NORMAL,
            cooldown=CooldownPeriod.TWENTY_FOUR_HOURS,
            status=AlertStatus.ACTIVE,
            notify_telegram=True,
        )
        session.add(alert)
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        # P/E needs to be ≤ 27 (30 * 0.9). Price = 27 * 6.42 = 173.34
        engine.price_provider.get_price.return_value = 160.0  # 160/6.42 ≈ 24.92 → -16.9%

        triggered = engine.check_all()
        assert len(triggered) == 1

    def test_historical_low_triggers(self, session, sample_ticker, aapl_fundamentals):
        """Historical low alert triggers when current value is at/below the historical min."""
        alert = Alert(
            ticker_id=sample_ticker.id,
            metric=MetricType.PE_TRAILING,
            condition=ConditionType.HISTORICAL_LOW,
            priority=AlertPriority.CRITICAL,
            cooldown=CooldownPeriod.TWENTY_FOUR_HOURS,
            status=AlertStatus.ACTIVE,
            notify_telegram=True,
        )
        session.add(alert)
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        # Very low price to hit historical low P/E
        engine.price_provider.get_price.return_value = 10.0  # 10/6.42 ≈ 1.56

        triggered = engine.check_all()
        assert len(triggered) == 1
        assert "NEW" in triggered[0].message and "LOW" in triggered[0].message

    def test_historical_low_retriggers_on_new_low(self, session, sample_ticker, aapl_fundamentals):
        """Historical low: re-triggers when a new lower value is set."""
        alert = Alert(
            ticker_id=sample_ticker.id,
            metric=MetricType.PE_TRAILING,
            condition=ConditionType.HISTORICAL_LOW,
            priority=AlertPriority.CRITICAL,
            cooldown=CooldownPeriod.TWENTY_FOUR_HOURS,
            status=AlertStatus.ACTIVE,
            notify_telegram=True,
            last_triggered_at=datetime.now(timezone.utc) - timedelta(hours=1),  # within cooldown
            last_triggered_value=2.0,  # triggered at P/E 2.0
        )
        session.add(alert)
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        # P/E = 10/6.42 ≈ 1.56 < 2.0 (previous triggered value) → new low, bypasses cooldown
        engine.price_provider.get_price.return_value = 10.0

        triggered = engine.check_all()
        assert len(triggered) == 1

    def test_historical_low_no_retrigger_if_not_new_low(self, session, sample_ticker, aapl_fundamentals):
        """Historical low: does NOT re-trigger if value is above last triggered value (within cooldown)."""
        alert = Alert(
            ticker_id=sample_ticker.id,
            metric=MetricType.PE_TRAILING,
            condition=ConditionType.HISTORICAL_LOW,
            priority=AlertPriority.CRITICAL,
            cooldown=CooldownPeriod.TWENTY_FOUR_HOURS,
            status=AlertStatus.ACTIVE,
            notify_telegram=True,
            last_triggered_at=datetime.now(timezone.utc) - timedelta(hours=1),
            last_triggered_value=1.0,  # already triggered at lower value
        )
        session.add(alert)
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        # P/E = 10/6.42 ≈ 1.56 > 1.0 → not a new low, still in cooldown
        engine.price_provider.get_price.return_value = 10.0

        triggered = engine.check_all()
        assert len(triggered) == 0


class TestCooldown:
    """Test cooldown/debounce logic."""

    def test_cooldown_blocks_retrigger(self, session, sample_ticker, aapl_fundamentals, sample_alert):
        """Same alert shouldn't trigger twice within cooldown period."""
        sample_alert.last_triggered_at = datetime.now(timezone.utc) - timedelta(hours=1)
        sample_alert.last_triggered_value = 23.0
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 150.0

        triggered = engine.check_all()
        assert len(triggered) == 0  # blocked by 24h cooldown

    def test_cooldown_allows_after_expiry(self, session, sample_ticker, aapl_fundamentals, sample_alert):
        """Alert should trigger again after cooldown expires."""
        sample_alert.last_triggered_at = datetime.now(timezone.utc) - timedelta(hours=25)
        sample_alert.last_triggered_value = 23.0
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 150.0

        triggered = engine.check_all()
        assert len(triggered) == 1


class TestAlertStates:
    """Test alert state transitions."""

    def test_paused_alert_not_checked(self, session, sample_ticker, aapl_fundamentals, sample_alert):
        """Paused alerts should not be evaluated."""
        sample_alert.status = AlertStatus.PAUSED
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 150.0

        triggered = engine.check_all()
        assert len(triggered) == 0

    def test_stopped_alert_not_checked(self, session, sample_ticker, aapl_fundamentals, sample_alert):
        """Stopped alerts should not be evaluated."""
        sample_alert.status = AlertStatus.STOPPED
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 150.0

        triggered = engine.check_all()
        assert len(triggered) == 0

    def test_absolute_alert_transitions_to_triggered(self, session, sample_ticker, aapl_fundamentals, sample_alert):
        """Absolute threshold alert should change status to TRIGGERED after firing."""
        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 150.0

        triggered = engine.check_all()
        assert len(triggered) == 1  # sanity check: it did fire
        session.flush()
        session.refresh(sample_alert)
        assert sample_alert.status == AlertStatus.TRIGGERED

    def test_historical_alert_stays_active(self, session, sample_ticker, aapl_fundamentals):
        """Historical extreme alerts stay ACTIVE after triggering to allow re-triggers."""
        alert = Alert(
            ticker_id=sample_ticker.id,
            metric=MetricType.PE_TRAILING,
            condition=ConditionType.HISTORICAL_LOW,
            priority=AlertPriority.CRITICAL,
            cooldown=CooldownPeriod.TWENTY_FOUR_HOURS,
            status=AlertStatus.ACTIVE,
            notify_telegram=True,
        )
        session.add(alert)
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 10.0

        engine.check_all()
        session.refresh(alert)
        assert alert.status == AlertStatus.ACTIVE  # stays active for re-triggering

    def test_unavailable_ticker_skipped(self, session, sample_ticker, aapl_fundamentals, sample_alert):
        """Tickers with UNAVAILABLE data status should be skipped."""
        sample_ticker.data_status = TickerDataStatus.UNAVAILABLE
        session.flush()

        engine = AlertEngine(session)
        engine.price_provider = MagicMock()
        engine.price_provider.get_price.return_value = 150.0

        triggered = engine.check_all()
        assert len(triggered) == 0
