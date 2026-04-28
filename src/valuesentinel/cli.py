"""CLI entry point for ValueSentinel."""

from __future__ import annotations

import argparse
import signal
import sys
import time

from valuesentinel.database import init_db
from valuesentinel.logging_config import get_logger, setup_logging
from valuesentinel.scheduler.jobs import run_check_cycle, start_scheduler, stop_scheduler

logger = get_logger("cli")


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(
        prog="valuesentinel",
        description="ValueSentinel — Financial Valuation Metrics Alerter",
    )
    sub = parser.add_subparsers(dest="command")

    # Run the scheduler
    sub.add_parser("run", help="Start the alert check scheduler")

    # Run a single check cycle
    sub.add_parser("check", help="Run a single check cycle and exit")

    # Initialize the database
    sub.add_parser("init-db", help="Create database tables")

    # Add a ticker
    add_p = sub.add_parser("add-ticker", help="Add a ticker to the watchlist")
    add_p.add_argument("symbol", help="Ticker symbol (e.g., AAPL, SHEL.L, 7203.T)")

    # Remove a ticker
    rm_p = sub.add_parser(
        "remove-ticker",
        help="Remove a ticker from the watchlist (also deletes its alerts and cached fundamentals)",
    )
    rm_p.add_argument("symbol", help="Ticker symbol to remove")
    rm_p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # Refresh fundamentals
    refresh_p = sub.add_parser("refresh", help="Refresh fundamental data")
    refresh_p.add_argument("symbol", nargs="?", help="Specific ticker (or all if omitted)")

    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
        logger.info("Database initialized")

    elif args.command == "add-ticker":
        _add_ticker(args.symbol)

    elif args.command == "remove-ticker":
        _remove_ticker(args.symbol, assume_yes=args.yes)

    elif args.command == "refresh":
        _refresh(args.symbol)

    elif args.command == "check":
        init_db()
        run_check_cycle()

    elif args.command == "run":
        init_db()
        logger.info("Starting ValueSentinel scheduler...")
        scheduler = start_scheduler()

        # Run one cycle immediately
        run_check_cycle()

        # Handle graceful shutdown
        def _shutdown(signum, frame):
            logger.info("Shutting down...")
            stop_scheduler()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            stop_scheduler()

    else:
        parser.print_help()


def _add_ticker(symbol: str) -> None:
    from valuesentinel.data.yfinance_connector import refresh_fundamentals, sync_ticker
    from valuesentinel.database import get_db

    init_db()
    with get_db() as session:
        ticker = sync_ticker(session, symbol)
        count = refresh_fundamentals(session, ticker)
        session.commit()
        print(
            f"Added {ticker.symbol} ({ticker.name}) — "
            f"{ticker.exchange}, {ticker.currency}, "
            f"{count} periods cached, "
            f"{ticker.history_years_available or 0:.1f}y history"
        )


def _remove_ticker(symbol: str, assume_yes: bool = False) -> None:
    from valuesentinel.database import get_db
    from valuesentinel.models import Ticker

    init_db()
    with get_db() as session:
        ticker = session.query(Ticker).filter(Ticker.symbol == symbol).first()
        if not ticker:
            print(f"Ticker {symbol} not found.")
            return

        alert_count = len(ticker.alerts)
        fundamentals_count = len(ticker.fundamentals)

        if not assume_yes:
            print(
                f"This will permanently remove {ticker.symbol} ({ticker.name or '?'}), "
                f"{alert_count} alert(s), and {fundamentals_count} cached fundamental period(s)."
            )
            answer = input("Continue? [y/N]: ").strip().lower()
            if answer not in ("y", "yes"):
                print("Aborted.")
                return

        session.delete(ticker)
        session.commit()
        print(f"Removed {symbol}")


def _refresh(symbol: str | None) -> None:
    from valuesentinel.data.yfinance_connector import refresh_fundamentals
    from valuesentinel.database import get_db
    from valuesentinel.models import Ticker

    init_db()
    with get_db() as session:
        if symbol:
            ticker = session.query(Ticker).filter(Ticker.symbol == symbol).first()
            if not ticker:
                print(f"Ticker {symbol} not found. Add it first with: valuesentinel add-ticker {symbol}")
                return
            count = refresh_fundamentals(session, ticker)
            session.commit()
            print(f"Refreshed {ticker.symbol}: {count} periods")
        else:
            tickers = session.query(Ticker).all()
            for t in tickers:
                count = refresh_fundamentals(session, t)
                print(f"  {t.symbol}: {count} periods")
            session.commit()
            print(f"Refreshed {len(tickers)} tickers")


if __name__ == "__main__":
    main()
