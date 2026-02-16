"""APScheduler job definitions for periodic alert checking and data refresh."""

from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from valuesentinel.alerts.engine import AlertEngine
from valuesentinel.config import get_config
from valuesentinel.database import get_db
from valuesentinel.logging_config import get_logger
from valuesentinel.notifications.manager import NotificationManager

logger = get_logger("scheduler")

_scheduler: BackgroundScheduler | None = None


def _is_earnings_season() -> bool:
    """Check if the current date falls within a US earnings season window."""
    now = datetime.now(timezone.utc)
    month, day = now.month, now.day
    windows = [
        (1, 15, 2, 28),
        (4, 15, 5, 31),
        (7, 15, 8, 31),
        (10, 15, 11, 30),
    ]
    for start_m, start_d, end_m, end_d in windows:
        if (month == start_m and day >= start_d) or (month == end_m and day <= end_d):
            return True
        if start_m < month < end_m:
            return True
    return False


def run_check_cycle() -> None:
    """Execute one alert check cycle: evaluate all active alerts, dispatch notifications."""
    logger.info("Starting check cycle")
    try:
        with get_db() as session:
            engine = AlertEngine(session)
            triggered = engine.check_all()

            if triggered:
                manager = NotificationManager()
                for history in triggered:
                    manager.dispatch(session, history)

            session.commit()
            logger.info("Check cycle complete — %d alerts triggered", len(triggered))
    except Exception:
        logger.exception("Check cycle failed")


def run_fundamental_refresh() -> None:
    """Refresh fundamental data for all watched tickers."""
    from valuesentinel.data.yfinance_connector import refresh_fundamentals
    from valuesentinel.models import Ticker

    logger.info("Starting fundamental data refresh")
    try:
        with get_db() as session:
            tickers = session.query(Ticker).all()
            for ticker in tickers:
                try:
                    refresh_fundamentals(session, ticker)
                except Exception:
                    logger.exception("Failed to refresh %s", ticker.symbol)
            session.commit()
            logger.info("Fundamental refresh complete for %d tickers", len(tickers))
    except Exception:
        logger.exception("Fundamental refresh failed")


def start_scheduler() -> BackgroundScheduler:
    """Initialize and start the APScheduler with all jobs."""
    global _scheduler

    cfg = get_config()
    _scheduler = BackgroundScheduler()

    # Alert check loop
    _scheduler.add_job(
        run_check_cycle,
        "interval",
        minutes=cfg.scheduler.check_interval_minutes,
        id="check_cycle",
        name="Alert Check Cycle",
        replace_existing=True,
    )

    # Fundamental data refresh — weekly on Sundays at 02:00 UTC
    _scheduler.add_job(
        run_fundamental_refresh,
        "cron",
        day_of_week="sun",
        hour=2,
        minute=0,
        id="weekly_refresh",
        name="Weekly Fundamental Refresh",
        replace_existing=True,
    )

    # During earnings season, also run daily at 03:00 UTC
    if _is_earnings_season():
        _scheduler.add_job(
            run_fundamental_refresh,
            "cron",
            hour=3,
            minute=0,
            id="earnings_daily_refresh",
            name="Earnings Season Daily Refresh",
            replace_existing=True,
        )
        logger.info("Earnings season detected — daily fundamental refresh enabled")

    _scheduler.start()
    logger.info(
        "Scheduler started: check every %d min, weekly refresh Sundays 02:00 UTC",
        cfg.scheduler.check_interval_minutes,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
        _scheduler = None
