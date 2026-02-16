"""Streamlit dashboard for ValueSentinel."""

from __future__ import annotations

import sys
import os

# Ensure src is on path when running via `streamlit run`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import streamlit as st
from datetime import datetime, timezone

from valuesentinel.calculator.valuation import ValuationCalculator
from valuesentinel.config import get_config
from valuesentinel.data.price_provider import PriceProviderFactory
from valuesentinel.data.yfinance_connector import refresh_fundamentals, sync_ticker
from valuesentinel.database import get_db, init_db
from valuesentinel.logging_config import setup_logging
from valuesentinel.models import (
    Alert,
    AlertHistory,
    AlertPriority,
    AlertStatus,
    ConditionType,
    CooldownPeriod,
    DeliveryStatus,
    METRIC_DISPLAY_NAMES,
    MetricType,
    Ticker,
    TickerDataStatus,
)
from valuesentinel.scheduler.jobs import run_check_cycle, start_scheduler

# ── Page config ──

st.set_page_config(
    page_title="ValueSentinel",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

setup_logging()
init_db()

# ── Sidebar navigation ──

st.sidebar.title("📊 ValueSentinel")
page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Create Alert", "Alert History", "Manage Tickers", "Settings"],
)

# ── Health status in sidebar ──

with get_db() as session:
    total_tickers = session.query(Ticker).count()
    active_alerts = session.query(Alert).filter(Alert.status == AlertStatus.ACTIVE).count()
    triggered_alerts = session.query(Alert).filter(Alert.status == AlertStatus.TRIGGERED).count()

st.sidebar.markdown("---")
st.sidebar.metric("Watched Tickers", total_tickers)
st.sidebar.metric("Active Alerts", active_alerts)
st.sidebar.metric("Triggered", triggered_alerts)

price_provider = PriceProviderFactory.get()
if price_provider.is_realtime():
    st.sidebar.success("🟢 IBKR Live Pricing")
else:
    st.sidebar.warning("🟡 Delayed Pricing (yfinance)")


# ══════════════════════════════════════════════════════
# PAGE: Dashboard
# ══════════════════════════════════════════════════════

if page == "Dashboard":
    st.title("Alert Dashboard")

    with get_db() as session:
        alerts = (
            session.query(Alert)
            .filter(Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.TRIGGERED]))
            .all()
        )

        if not alerts:
            st.info("No active alerts. Create one from the sidebar.")
        else:
            rows = []
            for alert in alerts:
                ticker = session.get(Ticker, alert.ticker_id)
                if not ticker:
                    continue

                metric_name = METRIC_DISPLAY_NAMES.get(alert.metric, alert.metric.value)

                # Get current value
                current_val = ""
                hist_min = ""
                hist_max = ""
                try:
                    price = price_provider.get_price(ticker.symbol)
                    if price:
                        calc = ValuationCalculator(session)
                        result = calc.compute_single(ticker, price, alert.metric)
                        if result and result.value is not None:
                            current_val = f"{result.value:.2f}"
                            hist_min = f"{result.historical_min:.2f}" if result.historical_min else "—"
                            hist_max = f"{result.historical_max:.2f}" if result.historical_max else "—"
                except Exception:
                    current_val = "Error"

                # Condition display
                cond_display = alert.condition.value
                if alert.threshold_value is not None:
                    if alert.condition in (ConditionType.ABSOLUTE_BELOW, ConditionType.ABSOLUTE_ABOVE):
                        op = "<" if alert.condition == ConditionType.ABSOLUTE_BELOW else ">"
                        cond_display = f"{op} {alert.threshold_value:.2f}"
                    elif alert.condition in (ConditionType.PERCENTAGE_DROP, ConditionType.PERCENTAGE_RISE):
                        sign = "-" if alert.condition == ConditionType.PERCENTAGE_DROP else "+"
                        cond_display = f"{sign}{alert.threshold_value:.1f}%"
                    else:
                        cond_display = alert.condition.value.replace("_", " ").title()
                else:
                    cond_display = alert.condition.value.replace("_", " ").title()

                priority_icon = {"critical": "🔴", "normal": "🟡", "informational": "🔵"}.get(
                    alert.priority.value, ""
                )
                status_icon = "🔴 Triggered" if alert.status == AlertStatus.TRIGGERED else "🟢 Active"
                timeframe = f"{ticker.history_years_available:.1f}y" if ticker.history_years_available else "—"

                rows.append({
                    "ID": alert.id,
                    "Ticker": ticker.symbol,
                    "Metric": metric_name,
                    "Condition": cond_display,
                    "Current": current_val,
                    "Min": hist_min,
                    "Max": hist_max,
                    "Timeframe": timeframe,
                    "Priority": priority_icon,
                    "Status": status_icon,
                })

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Alert controls
            st.subheader("Alert Controls")
            col1, col2, col3, col4, col5 = st.columns(5)
            alert_id = col1.number_input("Alert ID", min_value=1, step=1, value=1)

            with get_db() as session:
                if col2.button("⏸ Pause"):
                    alert = session.get(Alert, int(alert_id))
                    if alert:
                        alert.status = AlertStatus.PAUSED
                        session.commit()
                        st.success(f"Alert {alert_id} paused")
                        st.rerun()

                if col3.button("▶ Resume"):
                    alert = session.get(Alert, int(alert_id))
                    if alert:
                        alert.status = AlertStatus.ACTIVE
                        session.commit()
                        st.success(f"Alert {alert_id} resumed")
                        st.rerun()

                if col4.button("⏹ Stop"):
                    alert = session.get(Alert, int(alert_id))
                    if alert:
                        alert.status = AlertStatus.STOPPED
                        session.commit()
                        st.success(f"Alert {alert_id} stopped")
                        st.rerun()

                if col5.button("🗑 Remove"):
                    alert = session.get(Alert, int(alert_id))
                    if alert:
                        session.delete(alert)
                        session.commit()
                        st.success(f"Alert {alert_id} removed")
                        st.rerun()

            # ── Edit Alert ──
            st.subheader("Edit Alert")
            with get_db() as session:
                edit_id = st.number_input("Alert ID to edit", min_value=1, step=1, value=1, key="edit_id")
                edit_alert = session.get(Alert, int(edit_id))

                if edit_alert is None:
                    st.info(f"No alert found with ID {edit_id}.")
                else:
                    edit_ticker = session.get(Ticker, edit_alert.ticker_id)
                    st.caption(
                        f"**{edit_ticker.symbol if edit_ticker else '?'}** · "
                        f"{METRIC_DISPLAY_NAMES.get(edit_alert.metric, edit_alert.metric.value)} · "
                        f"Created {edit_alert.created_at.strftime('%Y-%m-%d') if edit_alert.created_at else '—'}"
                    )

                    ecol1, ecol2 = st.columns(2)

                    with ecol1:
                        new_condition = st.selectbox(
                            "Condition",
                            options=list(ConditionType),
                            index=list(ConditionType).index(edit_alert.condition),
                            format_func=lambda c: {
                                ConditionType.ABSOLUTE_BELOW: "Value < X",
                                ConditionType.ABSOLUTE_ABOVE: "Value > X",
                                ConditionType.PERCENTAGE_DROP: "Drop by X%",
                                ConditionType.PERCENTAGE_RISE: "Rise by X%",
                                ConditionType.HISTORICAL_LOW: "Historical Low (Rolling)",
                                ConditionType.HISTORICAL_HIGH: "Historical High (Rolling)",
                            }.get(c, c.value),
                            key="edit_condition",
                        )

                        needs_threshold = new_condition in (
                            ConditionType.ABSOLUTE_BELOW,
                            ConditionType.ABSOLUTE_ABOVE,
                            ConditionType.PERCENTAGE_DROP,
                            ConditionType.PERCENTAGE_RISE,
                        )
                        if needs_threshold:
                            th_label = "%" if new_condition in (
                                ConditionType.PERCENTAGE_DROP, ConditionType.PERCENTAGE_RISE
                            ) else "Value"
                            new_threshold = st.number_input(
                                f"Threshold ({th_label})",
                                value=float(edit_alert.threshold_value or 0),
                                format="%.2f",
                                key="edit_threshold",
                            )
                        else:
                            new_threshold = None

                    with ecol2:
                        new_priority = st.selectbox(
                            "Priority",
                            options=list(AlertPriority),
                            index=list(AlertPriority).index(edit_alert.priority),
                            format_func=lambda p: {
                                AlertPriority.CRITICAL: "🔴 Critical",
                                AlertPriority.NORMAL: "🟡 Normal",
                                AlertPriority.INFORMATIONAL: "🔵 Informational",
                            }.get(p, p.value),
                            key="edit_priority",
                        )

                        new_cooldown = st.selectbox(
                            "Cooldown",
                            options=list(CooldownPeriod),
                            index=list(CooldownPeriod).index(edit_alert.cooldown),
                            format_func=lambda c: c.value,
                            key="edit_cooldown",
                        )

                        st.markdown("**Notification Channels**")
                        new_telegram = st.checkbox("Telegram", value=edit_alert.notify_telegram, key="edit_tg")
                        new_discord = st.checkbox("Discord", value=edit_alert.notify_discord, key="edit_dc")
                        new_email = st.checkbox("Email", value=edit_alert.notify_email, key="edit_em")
                        new_pushover = st.checkbox("Pushover", value=edit_alert.notify_pushover, key="edit_po")

                    if st.button("💾 Save Changes", type="primary"):
                        edit_alert.condition = new_condition
                        edit_alert.threshold_value = new_threshold
                        edit_alert.priority = new_priority
                        edit_alert.cooldown = new_cooldown
                        edit_alert.notify_telegram = new_telegram
                        edit_alert.notify_discord = new_discord
                        edit_alert.notify_email = new_email
                        edit_alert.notify_pushover = new_pushover

                        # Recalculate baseline if switching to a percentage condition
                        if new_condition in (ConditionType.PERCENTAGE_DROP, ConditionType.PERCENTAGE_RISE):
                            if edit_ticker:
                                try:
                                    price = price_provider.get_price(edit_ticker.symbol)
                                    if price:
                                        calc = ValuationCalculator(session)
                                        result = calc.compute_single(edit_ticker, price, edit_alert.metric)
                                        if result and result.value is not None:
                                            edit_alert.baseline_value = result.value
                                except Exception:
                                    pass
                        else:
                            edit_alert.baseline_value = None

                        session.commit()
                        st.success(f"Alert {edit_id} updated successfully")
                        st.rerun()

    # Manual check
    st.markdown("---")
    if st.button("🔄 Run Check Cycle Now"):
        with st.spinner("Running check cycle..."):
            run_check_cycle()
        st.success("Check cycle complete")
        st.rerun()


# ══════════════════════════════════════════════════════
# PAGE: Create Alert
# ══════════════════════════════════════════════════════

elif page == "Create Alert":
    st.title("Create Alert")

    with get_db() as session:
        tickers = session.query(Ticker).order_by(Ticker.symbol).all()
        ticker_options = {f"{t.symbol} — {t.name}": t.id for t in tickers}

        if not ticker_options:
            st.warning("No tickers added yet. Go to **Manage Tickers** to add some.")
        else:
            col1, col2 = st.columns(2)

            with col1:
                selected_ticker = st.selectbox("Ticker", list(ticker_options.keys()))
                ticker_id = ticker_options[selected_ticker]

                metric = st.selectbox(
                    "Metric",
                    options=list(MetricType),
                    format_func=lambda m: METRIC_DISPLAY_NAMES.get(m, m.value),
                )

                condition = st.selectbox(
                    "Condition",
                    options=list(ConditionType),
                    format_func=lambda c: {
                        ConditionType.ABSOLUTE_BELOW: "Value < X",
                        ConditionType.ABSOLUTE_ABOVE: "Value > X",
                        ConditionType.PERCENTAGE_DROP: "Drop by X%",
                        ConditionType.PERCENTAGE_RISE: "Rise by X%",
                        ConditionType.HISTORICAL_LOW: "Historical Low (Rolling)",
                        ConditionType.HISTORICAL_HIGH: "Historical High (Rolling)",
                    }.get(c, c.value),
                )

            with col2:
                threshold = None
                if condition in (
                    ConditionType.ABSOLUTE_BELOW,
                    ConditionType.ABSOLUTE_ABOVE,
                    ConditionType.PERCENTAGE_DROP,
                    ConditionType.PERCENTAGE_RISE,
                ):
                    label = "%" if condition in (ConditionType.PERCENTAGE_DROP, ConditionType.PERCENTAGE_RISE) else "Value"
                    threshold = st.number_input(f"Threshold ({label})", value=0.0, format="%.2f")

                priority = st.selectbox(
                    "Priority",
                    options=list(AlertPriority),
                    index=1,  # Normal
                    format_func=lambda p: {
                        AlertPriority.CRITICAL: "🔴 Critical",
                        AlertPriority.NORMAL: "🟡 Normal",
                        AlertPriority.INFORMATIONAL: "🔵 Informational",
                    }.get(p, p.value),
                )

                cooldown = st.selectbox(
                    "Cooldown",
                    options=list(CooldownPeriod),
                    index=3,  # 24h
                    format_func=lambda c: c.value,
                )

                st.markdown("**Notification Channels**")
                notify_telegram = st.checkbox("Telegram", value=True)
                notify_discord = st.checkbox("Discord", value=False)
                notify_email = st.checkbox("Email", value=False)
                notify_pushover = st.checkbox("Pushover", value=False)

            if st.button("Create Alert", type="primary"):
                # Get baseline value for percentage conditions
                baseline = None
                if condition in (ConditionType.PERCENTAGE_DROP, ConditionType.PERCENTAGE_RISE):
                    ticker = session.get(Ticker, ticker_id)
                    if ticker:
                        price = price_provider.get_price(ticker.symbol)
                        if price:
                            calc = ValuationCalculator(session)
                            result = calc.compute_single(ticker, price, metric)
                            if result and result.value is not None:
                                baseline = result.value

                alert = Alert(
                    ticker_id=ticker_id,
                    metric=metric,
                    condition=condition,
                    threshold_value=threshold,
                    baseline_value=baseline,
                    priority=priority,
                    cooldown=cooldown,
                    status=AlertStatus.ACTIVE,
                    notify_telegram=notify_telegram,
                    notify_discord=notify_discord,
                    notify_email=notify_email,
                    notify_pushover=notify_pushover,
                )
                session.add(alert)
                session.commit()
                st.success(f"Alert created (ID: {alert.id})")


# ══════════════════════════════════════════════════════
# PAGE: Alert History
# ══════════════════════════════════════════════════════

elif page == "Alert History":
    st.title("Alert History")

    with get_db() as session:
        histories = (
            session.query(AlertHistory)
            .order_by(AlertHistory.triggered_at.desc())
            .limit(200)
            .all()
        )

        if not histories:
            st.info("No alert history yet.")
        else:
            rows = []
            for h in histories:
                alert = session.get(Alert, h.alert_id)
                ticker_symbol = "?"
                if alert:
                    ticker = session.get(Ticker, alert.ticker_id)
                    ticker_symbol = ticker.symbol if ticker else "?"

                rows.append({
                    "Time": h.triggered_at.strftime("%Y-%m-%d %H:%M UTC") if h.triggered_at else "",
                    "Ticker": ticker_symbol,
                    "Value": f"{h.metric_value:.2f}" if h.metric_value else "",
                    "Message": h.message[:120] if h.message else "",
                    "Delivery": h.delivery_status.value if h.delivery_status else "",
                    "Channels": h.delivery_channels or "",
                })

            df = pd.DataFrame(rows)

            # Filters
            col1, col2 = st.columns(2)
            filter_ticker = col1.text_input("Filter by ticker")
            filter_status = col2.selectbox(
                "Filter by delivery status",
                ["All"] + [s.value for s in DeliveryStatus],
            )

            if filter_ticker:
                df = df[df["Ticker"].str.contains(filter_ticker.upper())]
            if filter_status != "All":
                df = df[df["Delivery"] == filter_status]

            st.dataframe(df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════
# PAGE: Manage Tickers
# ══════════════════════════════════════════════════════

elif page == "Manage Tickers":
    st.title("Manage Tickers")

    # Add ticker
    st.subheader("Add Ticker")
    col1, col2 = st.columns([3, 1])
    new_symbol = col1.text_input(
        "Ticker symbol",
        placeholder="e.g., AAPL, SHEL.L, 7203.T",
    ).strip().upper()

    if col2.button("Add", type="primary") and new_symbol:
        with get_db() as session:
            try:
                with st.spinner(f"Fetching data for {new_symbol}..."):
                    ticker = sync_ticker(session, new_symbol)
                    count = refresh_fundamentals(session, ticker)
                    session.commit()
                st.success(
                    f"Added **{ticker.symbol}** ({ticker.name}) — "
                    f"{ticker.exchange}, {ticker.currency}, "
                    f"{count} periods, {ticker.history_years_available or 0:.1f}y history"
                )
                st.rerun()
            except Exception as e:
                st.error(f"Failed to add {new_symbol}: {e}")

    # Existing tickers
    st.subheader("Watchlist")
    with get_db() as session:
        tickers = session.query(Ticker).order_by(Ticker.symbol).all()
        if not tickers:
            st.info("No tickers added yet.")
        else:
            rows = []
            for t in tickers:
                status_icon = {
                    TickerDataStatus.OK: "🟢",
                    TickerDataStatus.DEGRADED: "⚠️",
                    TickerDataStatus.UNAVAILABLE: "🔴",
                }.get(t.data_status, "")

                rows.append({
                    "Symbol": t.symbol,
                    "Name": t.name or "",
                    "Exchange": t.exchange or "",
                    "Currency": t.currency or "",
                    "REIT": "✓" if t.is_reit else "",
                    "History": f"{t.history_years_available:.1f}y" if t.history_years_available else "—",
                    "Last Refresh": (
                        t.last_fundamental_refresh.strftime("%Y-%m-%d %H:%M")
                        if t.last_fundamental_refresh
                        else "Never"
                    ),
                    "Status": status_icon,
                })

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Refresh controls
            col1, col2 = st.columns(2)
            refresh_symbol = col1.text_input("Refresh specific ticker", placeholder="AAPL").strip().upper()

            if col1.button("🔄 Refresh"):
                with get_db() as session:
                    ticker = session.query(Ticker).filter(Ticker.symbol == refresh_symbol).first()
                    if ticker:
                        with st.spinner(f"Refreshing {refresh_symbol}..."):
                            count = refresh_fundamentals(session, ticker)
                            session.commit()
                        st.success(f"Refreshed {refresh_symbol}: {count} periods")
                        st.rerun()
                    else:
                        st.error(f"Ticker {refresh_symbol} not found")

            if col2.button("🔄 Refresh All"):
                with get_db() as session:
                    tickers = session.query(Ticker).all()
                    with st.spinner("Refreshing all tickers..."):
                        for t in tickers:
                            try:
                                refresh_fundamentals(session, t)
                            except Exception:
                                pass
                        session.commit()
                    st.success(f"Refreshed {len(tickers)} tickers")
                    st.rerun()


# ══════════════════════════════════════════════════════
# PAGE: Settings
# ══════════════════════════════════════════════════════

elif page == "Settings":
    st.title("Settings")

    cfg = get_config()

    st.subheader("Current Configuration")
    st.json({
        "database_url": cfg.db.url[:30] + "..." if len(cfg.db.url) > 30 else cfg.db.url,
        "check_interval_minutes": cfg.scheduler.check_interval_minutes,
        "telegram_configured": cfg.telegram.enabled,
        "discord_configured": cfg.discord.enabled,
        "email_configured": cfg.email.enabled,
        "log_level": cfg.logging.level,
    })

    st.info(
        "Configuration is managed via environment variables or `.env` file. "
        "See `.env.example` for all available options."
    )

    # Health check
    st.subheader("System Health")
    with get_db() as session:
        ticker_count = session.query(Ticker).count()
        alert_count = session.query(Alert).count()
        active_count = session.query(Alert).filter(Alert.status == AlertStatus.ACTIVE).count()
        history_count = session.query(AlertHistory).count()

    st.json({
        "tickers": ticker_count,
        "total_alerts": alert_count,
        "active_alerts": active_count,
        "history_entries": history_count,
        "pricing_mode": "IBKR (realtime)" if price_provider.is_realtime() else "yfinance (delayed)",
        "status": "healthy",
    })
