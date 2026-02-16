"""Alert checking engine — evaluates all active alerts each cycle."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from valuesentinel.calculator.valuation import MetricResult, ValuationCalculator
from valuesentinel.data.price_provider import PriceProviderFactory
from valuesentinel.logging_config import get_logger
from valuesentinel.models import (
    Alert,
    AlertHistory,
    AlertPriority,
    AlertStatus,
    ConditionType,
    CooldownPeriod,
    COOLDOWN_SECONDS,
    DeliveryStatus,
    METRIC_DISPLAY_NAMES,
    Ticker,
    TickerDataStatus,
)

logger = get_logger("alerts.engine")


class AlertEngine:
    """Evaluates all active alerts and produces trigger events."""

    def __init__(self, session: Session):
        self.session = session
        self.calculator = ValuationCalculator(session)
        self.price_provider = PriceProviderFactory.get()

    def check_all(self) -> list[AlertHistory]:
        """Run one full check cycle across all active alerts.

        Returns a list of newly triggered AlertHistory records.
        """
        active_alerts = (
            self.session.query(Alert)
            .filter(Alert.status == AlertStatus.ACTIVE)
            .all()
        )

        if not active_alerts:
            logger.debug("No active alerts to check")
            return []

        # Group alerts by ticker to avoid redundant price fetches
        alerts_by_ticker: dict[int, list[Alert]] = {}
        for alert in active_alerts:
            alerts_by_ticker.setdefault(alert.ticker_id, []).append(alert)

        triggered: list[AlertHistory] = []

        for ticker_id, alerts in alerts_by_ticker.items():
            ticker = self.session.get(Ticker, ticker_id)
            if ticker is None:
                continue

            if ticker.data_status == TickerDataStatus.UNAVAILABLE:
                logger.warning("Skipping %s — data unavailable", ticker.symbol)
                continue

            # Fetch live price once per ticker
            price = self.price_provider.get_price(ticker.symbol)
            if price is None:
                logger.warning("Could not get price for %s, skipping", ticker.symbol)
                continue

            for alert in alerts:
                result = self.calculator.compute_single(ticker, price, alert.metric)
                if result is None or result.value is None:
                    continue

                trigger_event = self._evaluate(alert, result)
                if trigger_event is not None:
                    triggered.append(trigger_event)

        logger.info(
            "Check cycle complete: %d alerts checked, %d triggered",
            len(active_alerts),
            len(triggered),
        )
        return triggered

    def _evaluate(self, alert: Alert, result: MetricResult) -> AlertHistory | None:
        """Evaluate a single alert against its current metric value."""

        # Check cooldown
        if not self._cooldown_elapsed(alert, result):
            return None

        condition_met = False
        message_parts: list[str] = []
        metric_name = METRIC_DISPLAY_NAMES.get(alert.metric, alert.metric.value)
        ticker = alert.ticker

        if alert.condition == ConditionType.ABSOLUTE_BELOW:
            if result.value is not None and alert.threshold_value is not None:
                if result.value < alert.threshold_value:
                    condition_met = True
                    message_parts.append(
                        f"{ticker.symbol} {metric_name} = {result.value:.2f} "
                        f"(below threshold {alert.threshold_value:.2f})"
                    )

        elif alert.condition == ConditionType.ABSOLUTE_ABOVE:
            if result.value is not None and alert.threshold_value is not None:
                if result.value > alert.threshold_value:
                    condition_met = True
                    message_parts.append(
                        f"{ticker.symbol} {metric_name} = {result.value:.2f} "
                        f"(above threshold {alert.threshold_value:.2f})"
                    )

        elif alert.condition == ConditionType.PERCENTAGE_DROP:
            if (
                result.value is not None
                and alert.baseline_value is not None
                and alert.baseline_value != 0
                and alert.threshold_value is not None
            ):
                pct_change = ((result.value - alert.baseline_value) / alert.baseline_value) * 100
                if pct_change <= -alert.threshold_value:
                    condition_met = True
                    message_parts.append(
                        f"{ticker.symbol} {metric_name} dropped {abs(pct_change):.1f}% "
                        f"from {alert.baseline_value:.2f} to {result.value:.2f}"
                    )

        elif alert.condition == ConditionType.PERCENTAGE_RISE:
            if (
                result.value is not None
                and alert.baseline_value is not None
                and alert.baseline_value != 0
                and alert.threshold_value is not None
            ):
                pct_change = ((result.value - alert.baseline_value) / alert.baseline_value) * 100
                if pct_change >= alert.threshold_value:
                    condition_met = True
                    message_parts.append(
                        f"{ticker.symbol} {metric_name} rose {pct_change:.1f}% "
                        f"from {alert.baseline_value:.2f} to {result.value:.2f}"
                    )

        elif alert.condition == ConditionType.HISTORICAL_LOW:
            if result.value is not None and result.historical_min is not None:
                if result.value <= result.historical_min:
                    # Rolling window: re-trigger on each new low
                    is_new_extreme = (
                        alert.last_triggered_value is None
                        or result.value < alert.last_triggered_value
                    )
                    if is_new_extreme or alert.last_triggered_at is None:
                        condition_met = True
                        message_parts.append(
                            f"🔻 {ticker.symbol} {metric_name} = {result.value:.2f} — "
                            f"NEW {result.timeframe_years:.1f}-YEAR LOW "
                            f"(prev low: {result.historical_min:.2f})"
                        )

        elif alert.condition == ConditionType.HISTORICAL_HIGH:
            if result.value is not None and result.historical_max is not None:
                if result.value >= result.historical_max:
                    is_new_extreme = (
                        alert.last_triggered_value is None
                        or result.value > alert.last_triggered_value
                    )
                    if is_new_extreme or alert.last_triggered_at is None:
                        condition_met = True
                        message_parts.append(
                            f"🔺 {ticker.symbol} {metric_name} = {result.value:.2f} — "
                            f"NEW {result.timeframe_years:.1f}-YEAR HIGH "
                            f"(prev high: {result.historical_max:.2f})"
                        )

        if not condition_met:
            return None

        # Build the full message
        timeframe_note = f"Calculated against {result.timeframe_years:.1f} years of data."
        ev_note = " [EV simplified]" if result.ev_simplified else ""
        currency_note = f" Currency: {result.currency}."
        full_message = " ".join(message_parts) + ev_note + "\n" + timeframe_note + currency_note

        # Build notification channel list
        channels = []
        if alert.notify_telegram:
            channels.append("telegram")
        if alert.notify_discord:
            channels.append("discord")
        if alert.notify_email:
            channels.append("email")
        if alert.notify_pushover:
            channels.append("pushover")

        # Create history record
        history = AlertHistory(
            alert_id=alert.id,
            triggered_at=datetime.now(timezone.utc),
            metric_value=result.value,
            threshold_value=alert.threshold_value,
            historical_min=result.historical_min,
            historical_max=result.historical_max,
            timeframe_years=result.timeframe_years,
            message=full_message,
            delivery_status=DeliveryStatus.PENDING,
            delivery_channels=",".join(channels),
            ev_simplified=result.ev_simplified,
        )
        self.session.add(history)

        # Update alert state
        alert.last_triggered_at = datetime.now(timezone.utc)
        alert.last_triggered_value = result.value
        alert.trigger_count = (alert.trigger_count or 0) + 1

        # Historical extremes stay ACTIVE to allow re-triggering
        if alert.condition not in (ConditionType.HISTORICAL_LOW, ConditionType.HISTORICAL_HIGH):
            alert.status = AlertStatus.TRIGGERED

        logger.info("TRIGGERED: %s", full_message)
        return history

    def _cooldown_elapsed(self, alert: Alert, result: MetricResult) -> bool:
        """Check if the cooldown period has elapsed since last trigger."""
        if alert.last_triggered_at is None:
            return True

        cooldown_secs = COOLDOWN_SECONDS.get(alert.cooldown, 86400)
        elapsed = (datetime.now(timezone.utc) - alert.last_triggered_at).total_seconds()

        if elapsed >= cooldown_secs:
            return True

        # Exception: Historical extremes bypass cooldown on NEW extremes
        if alert.condition in (ConditionType.HISTORICAL_LOW, ConditionType.HISTORICAL_HIGH):
            if result.value is not None and alert.last_triggered_value is not None:
                if alert.condition == ConditionType.HISTORICAL_LOW:
                    if result.value < alert.last_triggered_value:
                        return True  # New low bypasses cooldown
                elif alert.condition == ConditionType.HISTORICAL_HIGH:
                    if result.value > alert.last_triggered_value:
                        return True  # New high bypasses cooldown

        return False
