# **Product Requirements Document: ValueSentinel**

| Project Name | ValueSentinel \- Financial Metrics Alerter |
| :---- | :---- |
| **Version** | 1.1.0 |
| **Status** | Draft |
| **Last Updated** | 2026-02-16 |

---

**1\. Executive Summary**

**ValueSentinel** is a specialized financial monitoring tool designed to alert investors based on fundamental valuation metrics rather than simple price action. While traditional tools alert on price (e.g., "Stock hit $100"), ValueSentinel alerts on value (e.g., "P/E ratio dropped to 15x" or "EV/EBITDA is at a 10-year low"). It leverages free data sources for historical fundamentals and integrates with Interactive Brokers (IBKR) for real-time pricing, delivering alerts via Email, Telegram, and Discord.

---

**2\. Target Audience**

* **Value Investors:** Individuals looking to acquire companies only when they reach specific valuation multiples.  
* **Quantitative Traders:** Traders utilizing mean-reversion strategies based on historical valuation bands.  
* **Fundamental Analysts:** Users needing automated oversight of watchlist valuations without manual spreadsheet maintenance.

---

**3\. Assumptions & Constraints**

* **Single-User System (v1):** The initial release targets a single self-hosted user. Multi-user support is deferred.  
* **Global Equities:** The system must support equities listed on any major world exchange (US, Europe, Asia-Pacific, Emerging Markets). Tickers are identified using the exchange-suffixed format supported by yfinance (e.g., `AAPL` for US, `SHEL.L` for London, `7203.T` for Tokyo, `RELIANCE.NS` for India).  
* **Currency Handling:** All valuation metrics are computed in the **local currency** of the stock's listing exchange. Alerts display values in the stock's native currency. Cross-currency normalization or conversion is **not** performed — this avoids introducing FX noise into valuation comparisons.  
* **Free-Tier API Limits:** yfinance and Financial Modeling Prep free tier impose rate limits (typically ~250–300 requests/day for FMP). The system must operate within these constraints. This limits the practical watchlist to approximately **50–100 tickers** with a 15-minute check interval.  
* **IBKR Subscription Required:** Real-time pricing via IBKR requires an active brokerage account and either IB Gateway or TWS running locally. IBKR supports global exchanges natively.  
* **Reporting Lag & Frequency Variation:** Fundamental data is only as current as the most recent filing. Filing frequency and lag varies by jurisdiction — US companies report quarterly (SEC filings, 1–5 day API lag), while many international companies report semi-annually or annually. The system must handle all reporting cadences gracefully.  
* **Data Coverage Gaps:** Free data sources have weaker coverage for smaller international exchanges. If fundamental data is unavailable for a given ticker, the system must surface a clear "Data Unavailable" status rather than failing silently.

---

**4\. Out of Scope (v1)**

The following are explicitly **not** part of the v1 release:

* Backtesting engine or historical alert simulation.  
* Portfolio tracking, position sizing, or trade execution.  
* Technical analysis indicators (RSI, MACD, moving averages, etc.).  
* Forex, commodities, or crypto assets.  
* Cross-currency valuation comparisons or FX-adjusted metrics.  
* Multi-user accounts, authentication layers, or role-based access.  
* Mobile native application (web-responsive only).  
* Compound alert conditions (AND/OR logic across metrics) — planned for v2.

---

**5\. Functional Requirements**

### **5.1. Metrics & Data Handling**

The system must calculate and monitor the following valuation ratios:

* **Earnings Methods:** Price-to-Earnings (Trailing & Forward), EV/EBITDA, EV/EBIT.  
* **Cash Flow Methods:** Price-to-Free Cash Flow (P/FCF).  
* **REIT Specifics:** Price-to-FFO (Funds From Operations), Price-to-AFFO (Adjusted Funds From Operations).  
* **Asset/Revenue Methods:** Price-to-Book (P/B), Price-to-Sales (P/S).

**Historical Data Logic:**

* **Max Timeframe:** 10 years.  
* **Fallback Protocol:** Attempt 10 years \-\> If unavailable, use 5 years \-\> If unavailable, use maximum available history.  
* **Data Integrity:** All alerts must explicitly state the timeframe used for the calculation (e.g., *"Calculated against 6.5 years of available data"*).

**Corporate Actions:**

* The system must detect and adjust for **stock splits and reverse splits** to ensure per-share metrics (P/E, P/B, etc.) remain accurate across the historical window.  
* **Share buybacks** that materially change shares outstanding must trigger a fundamental data refresh.  
* Split-adjustment data from yfinance (adjusted close) should be used as the default.

**Forward P/E Data Source:**

* Forward earnings estimates are sourced from yfinance's `forwardEps` field (Yahoo Finance analyst consensus).  
* If `forwardEps` is unavailable for a ticker, the Forward P/E metric must be marked as **"N/A — No analyst estimates available"** rather than silently failing.

**Fundamental Data Refresh Trigger:**

* The system will check for new fundamental data on a **weekly schedule** (every Sunday at 02:00 UTC) for all watched tickers regardless of exchange.  
* Additionally, during US earnings season (Jan 15–Feb 28, Apr 15–May 31, Jul 15–Aug 31, Oct 15–Nov 30), checks for **all tickers** increase to **daily** — this also captures most international reporting periods.  
* For tickers on non-US exchanges that report semi-annually or annually, the system gracefully handles longer gaps between fundamental updates without marking the data as stale.  
* A manual "Refresh Fundamentals" button in the dashboard allows on-demand re-fetch for any ticker.

### **5.2. Alerting Logic**

The engine must support three triggering conditions:

1. **Absolute Threshold:** Trigger when metric $X$ crosses value $Y$ (e.g., "P/E \< 15").  
2. **Percentage Change:** Trigger when the valuation metric drops or rises by $Z\%$ relative to the value at the time of alert creation.  
3. **Historical Extremes (Rolling Window):** Trigger when the current metric reaches a new historical minimum or maximum within the defined rolling timeframe (e.g., "10-Year Low P/B"). The window rolls forward with time — a 10-year window always covers the trailing 10 years from the current date. **Re-triggering behavior:** If the stock sets a new extreme (e.g., hits a new 10-year low on Monday, then drops further on Tuesday), the alert **will re-trigger** on each new extreme, unless the user has explicitly **paused**, **stopped**, or **removed** the alert.

**Alert Priority Levels:**

Each alert must be assigned a priority level that determines notification behavior:

* 🔴 **Critical:** Immediate notification on all enabled channels. Used for Historical Extremes and Absolute Thresholds the user marks as high-priority.  
* 🟡 **Normal:** Notification delivered within the next scheduled check cycle (default for all alerts).  
* 🔵 **Informational:** Logged in alert history and visible on the dashboard, but no push notification is sent. Useful for passive monitoring.

**Cooldown & Debounce:**

* After an alert triggers, a configurable **cooldown period** (default: 24 hours) must elapse before the same ticker+metric+condition combination can trigger again.  
* **Exception:** Historical Extreme alerts bypass cooldown when a *new* extreme is set (i.e., the value moved further in the extreme direction).  
* Users can configure the cooldown per alert: 1 hour, 6 hours, 12 hours, 24 hours, 48 hours, or 1 week.

**Future Consideration (v2):**

* **Compound Conditions:** Support for AND/OR logic across metrics (e.g., "P/E \< 15 **AND** P/B \< 1.5"). This is deferred to v2 but the alert data model should be designed to accommodate it.

### **5.3. Integrations & Sources**

* **Primary Data (Historical/Fundamental):**  
  * **v1 Source:** yfinance (Python library). Provides historical financials, analyst estimates, and split-adjusted pricing for global equities across all major exchanges.  
  * **Fallback Source (v1.1):** Financial Modeling Prep (FMP) free tier, to be integrated as a secondary source if yfinance data is unavailable or stale. Note: FMP free tier has limited international coverage — yfinance remains the primary source for non-US equities.  
* **Secondary Data (Live Pricing):**  
  * **Interactive Brokers (IBKR):** Optional integration via IB Gateway/TWS API to fetch real-time pricing for highly accurate intraday valuation updates.  
  * **Fallback (no IBKR):** Use yfinance delayed quotes (~15 min delay) for users without an IBKR connection.  
* **Notification Channels:**  
  * **Email:** SMTP support.  
  * **Telegram:** Bot API integration.  
  * **Discord:** Webhook integration.

### **5.4. Dashboard (User Interface)**

A centralized dashboard to manage the lifecycle of alerts:

* **Active Alerts View:** Display current monitors with "Pause", "Stop", "Edit", and "Remove" capabilities.  
* **Alert History View:** A log of all triggered events, filterable by ticker, date, metric, or priority level.  
* **Re-arming:** Ability to restart a triggered alert (e.g., "Alert me again if it drops another 5%").  
* **Ticker Detail:** Display the current valuation status of a specific ticker against its historical range, including a visual band chart showing where the current value sits relative to historical min/max.  
* **Refresh Fundamentals:** Manual button to re-fetch fundamental data for a specific ticker on demand.

---

**6\. Non-Functional Requirements**

| Requirement | Target |
| :---- | :---- |
| **Alert Latency** | ≤ 5 minutes from condition met to notification delivered |
| **Uptime** | 99.5% (allows ~3.65 hours downtime/month for maintenance) |
| **Check Cycle** | Configurable: 5 min, 15 min (default), 30 min, 1 hour |
| **Max Watchlist Size** | 100 tickers per instance (constrained by free API limits) |
| **Dashboard Load Time** | \< 2 seconds for the main grid view |
| **Data Freshness** | Fundamental data no older than 7 days post-earnings release |
| **Notification Reliability** | ≥ 99% delivery rate (with retry logic) |

---

**7\. Security & Authentication**

* **v1 (Single User):** No user authentication layer. The application is accessed via localhost or a private network.  
* **API Key Storage:** All third-party API keys (FMP, Telegram Bot Token, Discord Webhook URL, SMTP credentials, IBKR) must be stored in **environment variables** or a `.env` file. Keys must **never** be committed to version control.  
* **IBKR Connection:** Communicates over localhost only (IB Gateway/TWS must run on the same machine or be SSH-tunneled).  
* **Notification Security:** Telegram Bot Token and Discord Webhook URLs are sensitive credentials — treat them as secrets.  
* **Future (v2):** When multi-user support is added, implement OAuth 2.0 or session-based authentication with per-user encrypted credential storage.

---

**8\. Error Handling & Resilience**

| Failure Scenario | Behavior |
| :---- | :---- |
| **yfinance API unreachable** | Retry 3× with exponential backoff (5s, 15s, 45s). Log warning. Use last cached data. If stale \> 48h, mark affected alerts as ⚠️ **Degraded** on the dashboard. |
| **IBKR disconnected** | Fall back to yfinance delayed quotes. Log warning and display a banner on the dashboard: "Live pricing unavailable — using delayed data." |
| **Fundamental data missing for ticker** | Mark ticker as ⚠️ **Data Unavailable**. Do not trigger alerts. Notify user once via their preferred channel. |
| **Notification channel failure** | Retry 3× with exponential backoff. If all retries fail, log the alert as **Delivered: Failed** in history and attempt delivery on next check cycle. |
| **Database unreachable** | Halt the check loop. Log critical error. Resume automatically when connection is restored. |
| **Malformed/unexpected API response** | Log the raw response for debugging. Skip the affected ticker for this cycle. Do not crash the application. |
| **Rate limit exceeded (429)** | Back off for the duration specified in the `Retry-After` header (or 60s default). Queue remaining checks for the next cycle. |

---

**9\. Technical Architecture**

### **9.1. Technology Stack**

* **Language:** Python 3.10+  
* **Database:**  
  * **Development:** SQLite — zero-config, file-based, suitable for local single-user use.  
  * **Production:** PostgreSQL — required for any deployment expecting high write throughput or future multi-user support.  
  * **Migration Path:** Use SQLAlchemy as the ORM to ensure DB-agnostic query code. Provide an Alembic migration script for SQLite → PostgreSQL migration.  
* **Frontend:** Streamlit (recommended for rapid visualization) or React.  
* **Scheduling:** APScheduler (for periodic background checks).  
* **Logging & Monitoring:**  
  * Structured logging via Python's `logging` module with JSON formatter.  
  * Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.  
  * Log rotation: 10 MB per file, retain last 5 files.  
  * Health-check endpoint (`/health`) returning system status: last check time, active alert count, data freshness, IBKR connection status.

### **9.2. Calculation Engine (The "Lazy" Strategy)**

To optimize for free API rate limits, the system will decouple Price from Fundamentals:

1. **Periodic Fetch:** Download and cache fundamental data (Earnings, EBITDA, Debt, Cash) only when new reports are released (see §5.1 Fundamental Data Refresh Trigger for schedule). Frequency adapts to each company's reporting cadence (quarterly, semi-annual, or annual).  
2. **Intraday Calculation:** Fetch *only* the live price.  
   * *Formula:*  
     $$Current\ Metric = \frac{Live\ Price}{Cached\ Fundamental\ Value}$$  
   * This ensures the heavy data (10 years of history) is not re-fetched unnecessarily.

**API Rate Limiting Strategy:**

* Maintain a request counter per source per day.  
* yfinance: Throttle to max 2,000 requests/day (self-imposed to avoid IP bans).  
* FMP free tier: Hard cap at 250 requests/day.  
* Distribute checks evenly across the check interval. For 100 tickers at 15-min intervals, this yields ~6.7 requests/minute — well within safe limits.

### **9.3. Standardized Formulas**

* **Enterprise Value (EV):**  
  $$EV = Market\ Cap + Total\ Debt + Preferred\ Equity + Minority\ Interest - Cash\ \&\ Equivalents$$  
  *Note: If Preferred Equity or Minority Interest data is unavailable from the free API, use the simplified formula (Market Cap + Total Debt - Cash) and annotate the alert with "EV (simplified)".*

* **FFO (REITs):**  
  $$FFO = Net\ Income + Depreciation + Amortization - Gains\ on\ Asset\ Sales$$  
  *Where available, use the REIT-reported FFO from filings (more reliable). Fall back to the calculated formula only when reported FFO is not available.*

* **AFFO (REITs):**  
  $$AFFO = FFO - Recurring\ CapEx$$  
  *Same precedence: prefer reported AFFO from filings over calculated values.*

---

**10\. UI Wireframe Concepts**

### **View A: Create Alert**

* **Input:** Ticker Symbol (e.g., AAPL).  
* **Selector:** Metric (Dropdown: EV/EBITDA, P/E, etc.).  
* **Condition:**  
  * Value \< X  
  * Value \> X  
  * Change \+/- %  
  * Is Historical High (Rolling Window)  
  * Is Historical Low (Rolling Window)  
* **Priority:** 🔴 Critical / 🟡 Normal (default) / 🔵 Informational  
* **Cooldown:** Dropdown (1h / 6h / 12h / 24h / 48h / 1 week)  
* **Toggles:** Send to \[x\] Email \[x\] Telegram \[x\] Discord.

### **View B: Dashboard Grid**

| Ticker | Metric | Condition | Current Value | Hist. Min | Hist. Max | Timeframe | Priority | Status | Controls |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **INTC** | P/B | \< 1.1 | 1.05 | 0.98 | 3.5 | 10y | 🔴 | 🔴 **Triggered** | \[Ack\] \[Pause\] \[Re-arm\] |
| **MSFT** | P/E | \< 25.0 | 32.1 | 22.0 | 45.0 | 10y | 🟡 | 🟢 Active | \[Edit\] \[Pause\] \[Stop\] |
| **O** | P/FFO | Hist. Low | 11.2 | 11.2 | 22.8 | 6.5y | 🔴 | 🔴 **New Low** | \[Ack\] \[Pause\] \[Stop\] |

*Note: "Timeframe" column reflects the actual data window used (may be less than 10y per the Fallback Protocol).*

---

**11\. Testing Strategy**

### **11.1. Unit Tests**

* **Valuation Calculator:** Validate every metric formula against hand-calculated values using known financial statements (e.g., AAPL Q3 2025 10-Q).  
* **Alert Engine:** Test each trigger type (absolute, percentage, historical extreme) with mock data confirming correct trigger/no-trigger behavior.  
* **Cooldown Logic:** Verify that cooldown windows are respected and that Historical Extreme bypass works correctly.  
* **Split Adjustment:** Confirm that a 2:1 split correctly adjusts historical per-share metrics.

### **11.2. Integration Tests**

* **yfinance Connector:** Verify data fetch, parse, and cache cycle for 7 representative tickers: US large-cap (AAPL), US small-cap, US REIT, ticker with limited history, ticker with recent split, European equity (e.g., SHEL.L), and Asian equity (e.g., 7203.T). Confirm correct exchange-suffix handling and local-currency metric computation.  
* **Notification Dispatchers:** Send test alerts to each channel and confirm delivery.  
* **IBKR Connector:** Verify connection, quote retrieval, and graceful fallback when IBKR is unavailable.

### **11.3. Validation Dataset**

* Maintain a `tests/fixtures/` directory with snapshot data for at least 7 tickers (including at least 2 non-US), enabling fully offline test runs.  
* Cross-reference calculated metrics against a trusted third-party source (e.g., Morningstar, GuruFocus) for at least 3 tickers (including at least 1 non-US) to validate accuracy within ±2%.

---

**12\. Data Retention & Privacy**

* **Alert History:** Retained indefinitely by default. Users can purge history older than a configurable threshold (30 / 90 / 180 / 365 days) from the dashboard.  
* **Cached Fundamental Data:** Retained for the full historical window (up to 10 years). Older data is overwritten on refresh, not accumulated.  
* **Personally Identifiable Information (PII):** The system stores **no PII** in v1 (single-user, no accounts). Notification channel credentials (email addresses, Telegram chat IDs) are stored in environment variables, not in the database.  
* **Log Files:** Rotated and retained for 30 days. Logs must not contain API keys or notification credentials — sanitize before writing.

---

**13\. Success Metrics / KPIs**

| Metric | Target | Measurement Method |
| :---- | :---- | :---- |
| **Alert Accuracy** | 100% of triggered alerts are mathematically correct | Automated validation tests against known values |
| **Alert Latency** | ≤ 5 minutes from condition met → notification delivered | Timestamp comparison in alert history log |
| **System Uptime** | ≥ 99.5% | Health-check endpoint monitoring |
| **Notification Delivery Rate** | ≥ 99% | Delivery status tracking in alert history |
| **Data Freshness** | Fundamentals updated within 7 days of earnings release | Comparison of cache timestamp vs. filing date |
| **False Positive Rate** | 0% (no alerts triggered on stale or erroneous data) | Cross-reference triggered alerts with live data source |

---

**14\. Implementation Roadmap**

### **Phase 0: Foundation (~1 week)**

* Project scaffolding: directory structure, virtual environment, dependency management (Poetry or pip-tools).  
* Database schema design and Alembic migration setup.  
* CI/CD pipeline: GitHub Actions for linting (ruff), type checking (mypy), and running tests on every push.  
* `.env.example` template with all required configuration keys.  
* **Milestone:** Repo is cloneable and `make setup && make test` passes with zero test stubs.

### **Phase 1: Data & Math Core (~2–3 weeks)**

* Build Python connector for yfinance with caching layer, rate-limit awareness, and exchange-suffix ticker support for global equities.  
* Implement the `ValuationCalculator` class with all formulas from §9.3, computing metrics in the stock's local currency.  
* Create the logic to normalize history (handle missing data, variable timeframes, stock splits, and varying reporting cadences across jurisdictions).  
* Build the periodic fundamental data refresh scheduler (§5.1).  
* Write unit tests and validation dataset (§11).  
* **Milestone:** For any supported ticker, the system can calculate all metrics and return the historical min/max/current values.  
* **MVP Gate:** Phase 1 completion + one notification channel (Telegram) constitutes a usable CLI-based MVP.  
* **Depends on:** Phase 0 complete.

### **Phase 2: Alerting Engine (~2 weeks)**

* Build the "Check Loop" (configurable interval, default 15 mins).  
* Implement all three trigger types (Absolute, Percentage, Historical Extreme with rolling window).  
* Implement cooldown logic and alert priority levels.  
* Implement Notification Dispatchers (Telegram first, then Discord, then Email).  
* Implement State Management (alert lifecycle: Active → Triggered → Acknowledged → Re-armed / Stopped).  
* **Milestone:** End-to-end test: create an alert, simulate a trigger, receive a notification.  
* **Depends on:** Phase 1 complete.

### **Phase 3: Interface & IBKR (~2–3 weeks)**

* Develop the Streamlit Dashboard (Views A and B from §10).  
* Integrate `ib_async` for live pricing data.  
* Implement the health-check endpoint.  
* Dockerize the application with `docker-compose.yml` (app + PostgreSQL).  
* Write integration tests for IBKR connector.  
* **Milestone:** Fully functional web dashboard with live data and Docker deployment.  
* **Depends on:** Phase 2 complete.