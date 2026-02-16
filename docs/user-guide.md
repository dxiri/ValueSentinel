# ValueSentinel — User Guide

> **Audience:** End users of the ValueSentinel dashboard who create and manage valuation alerts for stocks.

---

## Table of Contents

1. [What is ValueSentinel?](#1-what-is-valuesentinel)
2. [Accessing the Dashboard](#2-accessing-the-dashboard)
3. [Dashboard Overview](#3-dashboard-overview)
4. [Managing Your Watchlist](#4-managing-your-watchlist)
5. [Understanding Valuation Metrics](#5-understanding-valuation-metrics)
6. [Creating an Alert](#6-creating-an-alert)
7. [Editing an Alert](#7-editing-an-alert)
8. [Alert Controls (Pause, Resume, Stop, Remove)](#8-alert-controls-pause-resume-stop-remove)
9. [Reviewing Alert History](#9-reviewing-alert-history)
10. [Notification Channels](#10-notification-channels)
11. [Settings & Health](#11-settings--health)
12. [Tips & Best Practices](#12-tips--best-practices)
13. [FAQ](#13-faq)

---

## 1. What is ValueSentinel?

ValueSentinel is a financial alerting tool designed for **value investors**. It continuously monitors valuation metrics (like P/E, EV/EBITDA, P/B, P/FCF, etc.) for stocks on your watchlist and sends you notifications when specific conditions are met — for example, when a stock's trailing P/E drops below 15, or when its EV/EBITDA hits a new 10-year low.

**Key features:**
- Supports **all global exchanges** — US (AAPL), London (SHEL.L), Tokyo (7203.T), and more.
- 9 valuation metrics including REIT-specific P/FFO and P/AFFO.
- 6 alert condition types including rolling-window historical extremes.
- 4 notification channels: Telegram, Discord, Email, and Pushover.
- Automatic fundamental data refresh and configurable check intervals.

---

## 2. Accessing the Dashboard

Open your web browser and navigate to:

```
http://localhost:8501
```

(Your administrator may have deployed it on a different host or port — check with them.)

The sidebar on the left shows:
- **Navigation** — switch between the five pages.
- **Status indicators** — number of watched tickers, active alerts, and triggered alerts.
- **Pricing mode** — whether live (IBKR) or delayed (yfinance) pricing is in use.

---

## 3. Dashboard Overview

The **Dashboard** page is your main control center. It shows a table of all **Active** and **Triggered** alerts with live data:

| Column     | Description                                                    |
|------------|----------------------------------------------------------------|
| **ID**     | Unique alert identifier (used for editing and controls)        |
| **Ticker** | Stock symbol                                                   |
| **Metric** | The valuation metric being monitored                           |
| **Condition** | The trigger rule (e.g., "< 25.00", "Historical Low")       |
| **Current**   | The current calculated value of the metric                  |
| **Min / Max** | Historical minimum and maximum over the available timeframe |
| **Timeframe** | Years of historical data available                          |
| **Priority**  | 🔴 Critical, 🟡 Normal, or 🔵 Informational               |
| **Status**    | 🟢 Active or 🔴 Triggered                                  |

Below the table you will find **Alert Controls** and **Edit Alert** sections (see sections 7 and 8).

At the bottom, the **🔄 Run Check Cycle Now** button lets you manually trigger an immediate check across all active alerts without waiting for the next scheduled cycle.

---

## 4. Managing Your Watchlist

Navigate to **Manage Tickers** in the sidebar.

### Adding a Ticker

1. Type the ticker symbol in the text field. Use the exchange suffix for non-US stocks:
   - **US:** `AAPL`, `MSFT`, `O`
   - **London:** `SHEL.L`, `HSBA.L`
   - **Tokyo:** `7203.T`
   - **Frankfurt:** `SAP.DE`
   - **Hong Kong:** `0700.HK`
   - **Toronto:** `RY.TO`
   - **Paris:** `MC.PA`
2. Click **Add**.
3. ValueSentinel fetches the company's financial data (fundamentals, earnings history, etc.). This takes a few seconds.
4. On success, you'll see the company name, exchange, currency, number of data periods, and years of history.

### Viewing Your Watchlist

The **Watchlist** table shows all tracked tickers with:
- **Symbol** and **Name**
- **Exchange** and **Currency** (all metrics are calculated in the stock's local currency)
- **REIT** — whether the ticker is classified as a REIT (enables P/FFO and P/AFFO metrics)
- **History** — years of historical data available
- **Last Refresh** — when fundamental data was last updated
- **Status** — 🟢 OK, ⚠️ Degraded (partial data), or 🔴 Unavailable

### Refreshing Data

Fundamental data is refreshed **automatically** every week (Sundays at 02:00 UTC) and daily during earnings season (January, April, July, October). You can also refresh manually:

- **Refresh a single ticker** — type the symbol and click "🔄 Refresh".
- **Refresh all** — click "🔄 Refresh All" to update all tickers.

---

## 5. Understanding Valuation Metrics

ValueSentinel calculates valuation metrics using the **"Lazy Strategy"**: live (or delayed) stock price divided by cached fundamental values. This provides near-real-time metric updates without excessive API calls.

### Available Metrics

| Metric            | Formula                              | Applicable To    |
|-------------------|--------------------------------------|------------------|
| **P/E (Trailing)**| Price ÷ Trailing EPS                 | All stocks       |
| **P/E (Forward)** | Price ÷ Forward EPS (analyst est.)   | All stocks       |
| **EV/EBITDA**     | Enterprise Value ÷ EBITDA            | All stocks       |
| **EV/EBIT**       | Enterprise Value ÷ EBIT              | All stocks       |
| **P/FCF**         | Price ÷ Free Cash Flow per Share     | All stocks       |
| **P/B**           | Price ÷ Book Value per Share         | All stocks       |
| **P/S**           | Price ÷ Revenue per Share            | All stocks       |
| **P/FFO**         | Price ÷ Funds From Operations / Share| REITs only       |
| **P/AFFO**        | Price ÷ Adjusted FFO per Share       | REITs only       |

### Enterprise Value (EV)

EV is calculated as:

> **EV = Market Cap + Total Debt + Preferred Equity + Minority Interest − Cash**

If preferred equity and minority interest data is unavailable, a simplified formula is used (Market Cap + Debt − Cash), and the metric is annotated with **[EV simplified]** in notifications.

### Currency

All metrics are calculated in the **stock's local currency**. A stock listed on the London Stock Exchange (e.g., SHEL.L) will have values in GBP. This is noted in alert notifications.

### Historical Range

For each metric, ValueSentinel computes the **historical minimum and maximum** across a rolling window of up to 10 years of cached fundamental data. These values power the "Historical Low" and "Historical High" alert conditions.

---

## 6. Creating an Alert

Navigate to **Create Alert** in the sidebar.

### Step-by-Step

1. **Select a Ticker** — Choose from your watchlist (dropdown shows symbol and company name).

2. **Choose a Metric** — Pick the valuation metric to monitor (e.g., P/E Trailing, EV/EBITDA).

3. **Set the Condition** — Choose when the alert should fire:

   | Condition                      | How It Works                                                                 |
   |--------------------------------|------------------------------------------------------------------------------|
   | **Value < X**                  | Triggers when the metric drops below your threshold                          |
   | **Value > X**                  | Triggers when the metric rises above your threshold                          |
   | **Drop by X%**                 | Triggers when the metric drops by X% from the value at alert creation        |
   | **Rise by X%**                 | Triggers when the metric rises by X% from the value at alert creation        |
   | **Historical Low (Rolling)**   | Triggers when the metric reaches a new all-time low in the rolling window    |
   | **Historical High (Rolling)**  | Triggers when the metric reaches a new all-time high in the rolling window   |

4. **Set the Threshold** (for value and percentage conditions) — Enter the numeric threshold. For percentage conditions, enter the percentage (e.g., `10` for 10%).

5. **Choose Priority**:
   - 🔴 **Critical** — immediate notification with highest urgency.
   - 🟡 **Normal** — standard notification (default).
   - 🔵 **Informational** — logged in dashboard only, **no push notifications sent**.

6. **Set Cooldown** — How long to wait after triggering before the same alert can fire again:
   - 1 hour, 6 hours, 12 hours, **24 hours** (default), 48 hours, or 1 week.

7. **Select Notification Channels** — Check which channels should receive notifications: Telegram, Discord, Email, and/or Pushover.

8. Click **Create Alert**.

### Example Alerts

- *"Notify me on Telegram when Apple's trailing P/E drops below 20"*
  - Ticker: AAPL, Metric: P/E (Trailing), Condition: Value < X, Threshold: 20, Channel: Telegram

- *"Alert me when Shell's EV/EBITDA hits a new 10-year low"*
  - Ticker: SHEL.L, Metric: EV/EBITDA, Condition: Historical Low (Rolling), Channel: Pushover

- *"Send a Pushover alert if Realty Income's P/FFO drops 15% from today's level"*
  - Ticker: O, Metric: P/FFO, Condition: Drop by X%, Threshold: 15, Channel: Pushover

---

## 7. Editing an Alert

On the **Dashboard** page, scroll below the alert table to the **Edit Alert** section.

1. Enter the **Alert ID** you want to modify (visible in the "ID" column of the alert table).
2. The current alert details are displayed. You can change:
   - **Condition** and **Threshold**
   - **Priority**
   - **Cooldown** period
   - **Notification Channels** (Telegram, Discord, Email, Pushover)
3. Click **💾 Save Changes**.

> **Note:** If you switch to a percentage-based condition (Drop by X% or Rise by X%), the baseline is automatically recalculated from the current metric value.

---

## 8. Alert Controls (Pause, Resume, Stop, Remove)

On the **Dashboard** page, use the **Alert Controls** section:

1. Enter the **Alert ID**.
2. Click the desired action:

| Action       | Effect                                                                |
|--------------|-----------------------------------------------------------------------|
| **⏸ Pause**  | Temporarily suspends the alert. It will not be checked until resumed. |
| **▶ Resume** | Reactivates a paused or triggered alert back to Active status.        |
| **⏹ Stop**   | Permanently deactivates the alert. Can be resumed if needed.          |
| **🗑 Remove** | Permanently deletes the alert and all its history.                    |

### Alert Status Lifecycle

```
                    ┌──────────┐
          ┌────────►│  PAUSED  │◄──── User pauses
          │         └────┬─────┘
          │              │ User resumes
          │              ▼
     ┌────┴─────┐   ┌──────────┐     Condition met    ┌───────────┐
     │  ACTIVE  │──►│ TRIGGERED│────────────────────► │ACKNOWLEDGED│
     └──────────┘   └──────────┘                       └───────────┘
          │              │
          │              │ User stops
          │              ▼
          │         ┌──────────┐
          └────────►│  STOPPED │
                    └──────────┘
```

**Important:** Historical Low and Historical High alerts **stay Active** after triggering (they don't transition to Triggered). This allows them to re-fire when a new extreme is reached, even within the cooldown period if the new value is more extreme than the last triggered value.

---

## 9. Reviewing Alert History

Navigate to **Alert History** in the sidebar.

This page displays a log of every alert that has fired, with:

| Column       | Description                                    |
|--------------|------------------------------------------------|
| **Time**     | When the alert triggered (UTC)                 |
| **Ticker**   | Stock symbol                                   |
| **Value**    | The metric value that triggered the alert      |
| **Message**  | Full alert message with details                |
| **Delivery** | Notification status (delivered, failed, pending)|
| **Channels** | Which channels received the notification       |

### Filtering

Use the filters at the top:
- **Filter by ticker** — type a ticker symbol to show only that stock's alerts.
- **Filter by delivery status** — filter by Delivered, Failed, or Pending.

The history shows the most recent **200 entries**.

---

## 10. Notification Channels

When an alert triggers, notifications are sent to all channels you selected when creating the alert. Each notification includes:

- The alert condition and current metric value
- The threshold or historical context
- The historical min/max range and timeframe
- Currency and any annotations (e.g., [EV simplified])

### Channel Summary

| Channel      | Delivery Method                      | Setup Required         |
|--------------|--------------------------------------|------------------------|
| **Telegram** | Instant message via bot              | Bot token + chat ID    |
| **Discord**  | Webhook message to a channel         | Webhook URL            |
| **Email**    | Email via SMTP                       | SMTP server credentials|
| **Pushover** | Push notification to phone/desktop   | User key + API token   |

### Priority Behavior

- **Critical** alerts are sent immediately to all selected channels.
- **Normal** alerts are sent normally to all selected channels.
- **Informational** alerts are **not** sent as push notifications — they only appear in the Alert History on the dashboard.

### Cooldown

After an alert fires, it enters a **cooldown period** (configurable per alert: 1h to 1 week). During cooldown, the same alert will not fire again even if the condition is still met. This prevents notification spam.

**Exception:** Historical Low/High alerts bypass the cooldown if a **new extreme** is detected (e.g., a new all-time low that is even lower than the value that last triggered the alert).

---

## 11. Settings & Health

Navigate to **Settings** in the sidebar.

### Current Configuration

Shows a summary of the active configuration:
- Database URL (truncated for security)
- Check interval
- Which notification channels are configured
- Log level

> Configuration is managed by your administrator via environment variables. Changes require a service restart.

### System Health

Displays:
- Number of tracked tickers and total alerts
- Number of active alerts and history entries
- Current pricing mode (IBKR realtime or yfinance delayed)

---

## 12. Tips & Best Practices

### Choosing the Right Metric

| Goal                                       | Recommended Metric      |
|--------------------------------------------|-------------------------|
| General "cheapness" check                  | P/E (Trailing)          |
| Growth stock valuation                     | P/E (Forward)           |
| Capital-intensive businesses               | EV/EBITDA or EV/EBIT    |
| Assessing cash generation                  | P/FCF                   |
| Bank or asset-heavy company                | P/B                     |
| High-revenue, low-margin company           | P/S                     |
| REIT valuation                             | P/FFO or P/AFFO         |

### Choosing the Right Condition

- Use **Value < X** (absolute below) when you have a specific fair-value target in mind.
- Use **Historical Low (Rolling)** when you want to be notified of rare, potentially once-in-a-decade opportunities — no threshold needed.
- Use **Drop by X%** when you want to monitor relative changes from today's value.

### Cooldown Strategy

- **1 hour** — for rapidly moving situations you're actively monitoring.
- **24 hours** (default) — good for daily awareness without spam.
- **1 week** — for long-term investments where you check weekly.

### Notification Channels

- Use **Pushover** or **Telegram** for immediate mobile alerts.
- Use **Email** for a permanent record you can search later.
- Use **Discord** for team-based investing or sharing alerts with a group.
- Use multiple channels on **Critical** alerts for redundancy.

---

## 13. FAQ

**Q: How often are alerts checked?**
A: By default, every 15 minutes. Your administrator can adjust this via `CHECK_INTERVAL_MINUTES`.

**Q: Are the stock prices real-time?**
A: By default, prices come from yfinance with approximately 15-minute delay. If Interactive Brokers is configured, real-time prices are used. The sidebar shows "🟢 IBKR Live Pricing" or "🟡 Delayed Pricing (yfinance)".

**Q: How far back does historical data go?**
A: Up to 10 years, depending on what's available from the data provider. The exact range is shown per ticker in the "History" column on the Manage Tickers page and per alert as "Timeframe" on the Dashboard.

**Q: What happens when a threshold alert triggers?**
A: The alert status changes to **Triggered** and a notification is sent. To re-arm it, click **▶ Resume** on the Dashboard to set it back to Active.

**Q: What happens when a Historical Low/High alert triggers?**
A: It stays **Active** automatically and will trigger again when a new extreme is detected, even bypassing the cooldown if the new value is more extreme.

**Q: Why didn't I receive a notification?**
A: Check the **Alert History** page for delivery status. Common reasons:
- The notification channel is not configured (check Settings page).
- The alert priority is set to Informational (no push notifications).
- The alert is Paused or Stopped.
- The alert is within its cooldown period.

**Q: Can I monitor stocks from any country?**
A: Yes. ValueSentinel supports all exchanges available through yfinance. Use the appropriate suffix: `.L` (London), `.T` (Tokyo), `.DE` (Frankfurt), `.HK` (Hong Kong), `.TO` (Toronto), `.PA` (Paris), etc. US stocks use no suffix.

**Q: What's the [EV simplified] annotation?**
A: This means the Enterprise Value was calculated using a simplified formula (Market Cap + Debt − Cash) because preferred equity and minority interest data was unavailable. The metric is still valid but may be slightly less precise for companies with significant preferred stock.

**Q: Can I create multiple alerts for the same ticker?**
A: Yes. You can have different alerts for different metrics, conditions, or thresholds on the same stock.

**Q: What is the P/FFO and P/AFFO metric?**
A: These are REIT-specific metrics. **FFO** (Funds From Operations) adds back depreciation to net income, which is more meaningful for real estate companies since property values don't depreciate the same way as other assets. **AFFO** (Adjusted FFO) further adjusts for recurring capital expenditures. These metrics only appear for tickers classified as REITs.
