# ValueSentinel — Deployment Guide

> **Audience:** Engineers and system administrators deploying ValueSentinel in development or production environments.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Architecture Overview](#2-architecture-overview)
3. [Option A — Docker Compose (Recommended for Production)](#3-option-a--docker-compose-recommended-for-production)
4. [Option B — Local / Bare-Metal](#4-option-b--local--bare-metal)
5. [Environment Variables Reference](#5-environment-variables-reference)
6. [Database & Migrations](#6-database--migrations)
7. [Notification Channel Setup](#7-notification-channel-setup)
8. [IBKR Real-Time Pricing (Optional)](#8-ibkr-real-time-pricing-optional)
9. [CLI Reference](#9-cli-reference)
10. [Health Monitoring](#10-health-monitoring)
11. [Logging](#11-logging)
12. [Backup & Data Retention](#12-backup--data-retention)
13. [Updating / Upgrading](#13-updating--upgrading)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Prerequisites

| Requirement            | Minimum Version | Notes                                      |
|------------------------|----------------|--------------------------------------------|
| **Docker + Compose**   | 24.x / v2      | For Docker deployment                      |
| **Python**             | 3.10+          | For local deployment                       |
| **PostgreSQL**         | 14+            | Production database (Docker provides 16)   |
| **Git**                | any            | To clone the repository                    |

Hardware: ValueSentinel is lightweight — 1 CPU core, 512 MB RAM, and 1 GB disk is sufficient for up to ~200 tickers.

---

## 2. Architecture Overview

ValueSentinel runs as three services:

```
┌─────────────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│     app (Streamlit)  │    │    scheduler (CLI)   │    │   db (PostgreSQL)│
│   Dashboard on :8501 │    │  APScheduler loop    │    │   Data store     │
│   Alembic on startup │    │  Checks every N min  │    │   Port 5432      │
└─────────┬───────────┘    └─────────┬───────────┘    └────────┬─────────┘
          │                          │                          │
          └──────────────────────────┴──────────────────────────┘
                              DATABASE_URL
```

- **app** — Streamlit dashboard (port 8501). Runs Alembic migrations on startup, then serves the UI.
- **scheduler** — Background process that runs alert check cycles on a configurable interval (default: 15 min) and refreshes fundamental data weekly.
- **db** — PostgreSQL 16. SQLite can be used for development but is not recommended for production.

Data flows:
- **yfinance** is the default data source for fundamentals and delayed price quotes.
- **IBKR (Interactive Brokers)** can optionally replace yfinance for real-time pricing if configured.
- Notifications are dispatched to **Telegram**, **Discord**, **Email (SMTP)**, and/or **Pushover** when alerts trigger.

---

## 3. Option A — Docker Compose (Recommended for Production)

### 3.1 Clone & Configure

```bash
git clone <repository-url> ValueSentinel
cd ValueSentinel
cp .env.example .env
```

Edit `.env` with your notification credentials and any overrides. The `DATABASE_URL` is set automatically inside `docker-compose.yml` for the PostgreSQL container — you do **not** need to set it in `.env` for Docker deployments.

### 3.2 Build & Start

```bash
docker compose build
docker compose up -d
```

This starts all three services. On first boot, Alembic runs all migrations automatically.

### 3.3 Verify

```bash
# Check all containers are running
docker compose ps

# Check logs
docker compose logs --tail=20

# Confirm dashboard is reachable
curl -s http://localhost:8501 | head -5
```

You should see:
- `app` — "You can now view your Streamlit app in your browser"
- `scheduler` — "Scheduler started: check every 15 min"
- `db` — "database system is ready to accept connections"

### 3.4 Stop / Restart

```bash
docker compose down          # Stop all services
docker compose up -d         # Start again
docker compose restart app   # Restart just the dashboard
```

### 3.5 Persistent Data

The PostgreSQL data volume (`pgdata`) persists across restarts. Logs are mounted at `./logs/` on the host.

To destroy all data and start fresh:

```bash
docker compose down -v   # -v removes named volumes
```

---

## 4. Option B — Local / Bare-Metal

### 4.1 Create Virtual Environment

```bash
cd ValueSentinel
python3 -m venv .venv
source .venv/bin/activate
```

### 4.2 Install

```bash
# Development (with test tools)
pip install -e ".[dev]"

# Production (with PostgreSQL driver)
pip install -e ".[postgres]"

# Everything
pip install -e ".[all]"
```

### 4.3 Configure

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL, notification keys, etc.
```

For local development, `DATABASE_URL` defaults to `sqlite:///data/valuesentinel.db`, which requires no external database.

### 4.4 Initialize Database

```bash
# Create tables via Alembic
alembic upgrade head

# Or via CLI
python -m valuesentinel init-db
```

### 4.5 Add Tickers & Run

```bash
# Add a ticker
python -m valuesentinel add-ticker AAPL
python -m valuesentinel add-ticker SHEL.L

# Run a single check cycle
python -m valuesentinel check

# Start the scheduler (background monitoring)
python -m valuesentinel run
```

### 4.6 Start the Dashboard

In a separate terminal:

```bash
source .venv/bin/activate
streamlit run src/valuesentinel/dashboard/app.py
```

Dashboard opens at **http://localhost:8501**.

### 4.7 Makefile Shortcuts

```bash
make setup       # Install deps, init DB, copy .env
make test        # Run pytest
make lint        # Ruff linter
make typecheck   # mypy strict
make run         # Start scheduler
make dashboard   # Start Streamlit
make migrate     # Run Alembic migrations
```

---

## 5. Environment Variables Reference

All configuration is via environment variables (or a `.env` file loaded automatically).

### Core

| Variable                  | Default                               | Description                                      |
|---------------------------|---------------------------------------|--------------------------------------------------|
| `DATABASE_URL`            | `sqlite:///data/valuesentinel.db`     | SQLAlchemy connection string                     |
| `CHECK_INTERVAL_MINUTES`  | `15`                                  | Minutes between alert check cycles               |
| `LOG_LEVEL`               | `INFO`                                | Python logging level (DEBUG, INFO, WARNING, etc) |
| `LOG_FILE`                | `logs/valuesentinel.log`              | Path to log file                                 |

### Telegram

| Variable              | Default | Description                            |
|-----------------------|---------|----------------------------------------|
| `TELEGRAM_BOT_TOKEN`  | —       | Bot token from @BotFather              |
| `TELEGRAM_CHAT_ID`    | —       | Chat/group ID for notifications        |

### Discord

| Variable              | Default | Description                            |
|-----------------------|---------|----------------------------------------|
| `DISCORD_WEBHOOK_URL` | —       | Full webhook URL for the channel       |

### Email (SMTP)

| Variable              | Default | Description                            |
|-----------------------|---------|----------------------------------------|
| `SMTP_HOST`           | —       | SMTP server hostname                   |
| `SMTP_PORT`           | `587`   | SMTP port (587 for TLS, 465 for SSL)  |
| `SMTP_USERNAME`       | —       | SMTP auth username                     |
| `SMTP_PASSWORD`       | —       | SMTP auth password                     |
| `SMTP_FROM_ADDRESS`   | —       | Sender email address                   |
| `SMTP_TO_ADDRESS`     | —       | Recipient email address                |

### Pushover

| Variable              | Default | Description                            |
|-----------------------|---------|----------------------------------------|
| `PUSHOVER_USER_KEY`   | —       | Your Pushover user key                 |
| `PUSHOVER_API_TOKEN`  | —       | Your Pushover application API token    |

### Interactive Brokers (Optional)

| Variable              | Default     | Description                          |
|-----------------------|-------------|--------------------------------------|
| `IBKR_HOST`           | `127.0.0.1` | IBKR Gateway/TWS host               |
| `IBKR_PORT`           | `7497`      | IBKR Gateway/TWS port               |
| `IBKR_CLIENT_ID`      | `1`         | IBKR client ID                       |

---

## 6. Database & Migrations

ValueSentinel uses **Alembic** for schema migrations. Migrations run automatically on Docker startup (the `app` container runs `alembic upgrade head` before launching Streamlit).

### Manual migration commands

```bash
# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current

# View migration history
alembic history

# Downgrade one step
alembic downgrade -1
```

### Current migrations

| Revision | Description                                       |
|----------|---------------------------------------------------|
| `001`    | Initial schema (tickers, fundamental_data, alerts, alert_history) |
| `002`    | Widen enum string columns for full enum value names |
| `003`    | Add `notify_pushover` column to alerts             |

### PostgreSQL vs SQLite

- **SQLite** — Zero-config, suitable for local dev and single-user setups. Data file at `data/valuesentinel.db`.
- **PostgreSQL** — Recommended for production. Supports concurrent access from `app` and `scheduler` containers. The Docker Compose setup provisions a PostgreSQL 16 instance automatically.

---

## 7. Notification Channel Setup

At least one notification channel should be configured for alerts to be delivered. Unconfigured channels are silently skipped. Alerts with **Informational** priority never generate push notifications (dashboard-only).

### Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram.
2. Copy the bot token → set `TELEGRAM_BOT_TOKEN`.
3. Start a chat with your bot, then get the chat ID (use [@userinfobot](https://t.me/userinfobot) or the Telegram Bot API `getUpdates` endpoint) → set `TELEGRAM_CHAT_ID`.

### Discord

1. In your Discord server, go to **Server Settings → Integrations → Webhooks**.
2. Create a webhook for the target channel.
3. Copy the webhook URL → set `DISCORD_WEBHOOK_URL`.

### Email (SMTP)

Use any SMTP provider (Gmail, SendGrid, AWS SES, etc.). Example for Gmail:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=yourname@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_ADDRESS=yourname@gmail.com
SMTP_TO_ADDRESS=recipient@example.com
```

> **Note:** Gmail requires an [App Password](https://support.google.com/accounts/answer/185833) if 2FA is enabled.

### Pushover

1. Create an account at [pushover.net](https://pushover.net).
2. Copy your **User Key** from the dashboard → set `PUSHOVER_USER_KEY`.
3. [Create an Application/API Token](https://pushover.net/apps/build) → set `PUSHOVER_API_TOKEN`.
4. Install the Pushover app on your phone/desktop to receive notifications.

### Retry & Rate Limiting

All dispatchers retry up to **3 times** with exponential backoff on failure. Telegram and Pushover also respect rate-limit headers (HTTP 429) and wait the indicated duration before retrying.

---

## 8. IBKR Real-Time Pricing (Optional)

By default, ValueSentinel uses **yfinance** for 15-minute delayed quotes. For real-time pricing:

1. Run IBKR Gateway or Trader Workstation (TWS) with API access enabled.
2. Set `IBKR_HOST`, `IBKR_PORT`, and `IBKR_CLIENT_ID` in your `.env`.
3. Install the optional dependency: `pip install valuesentinel[ibkr]`

The system auto-detects IBKR availability on startup. If the connection fails, it falls back to yfinance with a logged warning.

---

## 9. CLI Reference

```
valuesentinel <command> [args]
```

| Command                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| `init-db`                | Create database tables (safe to re-run)               |
| `add-ticker <SYMBOL>`   | Add a ticker to the watchlist and fetch fundamentals   |
| `refresh [SYMBOL]`      | Refresh fundamental data (specific ticker or all)      |
| `check`                 | Run a single alert check cycle and exit                |
| `run`                   | Start the scheduler (continuous monitoring)            |

Examples:

```bash
python -m valuesentinel init-db
python -m valuesentinel add-ticker AAPL
python -m valuesentinel add-ticker 7203.T     # Toyota (Tokyo)
python -m valuesentinel add-ticker SHEL.L     # Shell (London)
python -m valuesentinel refresh               # Refresh all tickers
python -m valuesentinel check                 # One-time check
python -m valuesentinel run                   # Start scheduler
```

---

## 10. Health Monitoring

### Dashboard Health

The **Settings** page in the dashboard shows a live health summary: ticker count, active alerts, history entries, and pricing mode.

### HTTP Health Endpoint

The application includes a health check module at `valuesentinel.health` that can be enabled for monitoring. The Docker `db` service has a built-in health check via `pg_isready`.

### Docker Health

```bash
docker compose ps         # Service status
docker compose logs -f    # Live logs
```

---

## 11. Logging

Logs are written to both **stdout** (for Docker log collection) and a rotating file.

| Setting     | Default                    | Notes                           |
|-------------|----------------------------|---------------------------------|
| `LOG_LEVEL` | `INFO`                     | Set to `DEBUG` for verbose logs |
| `LOG_FILE`  | `logs/valuesentinel.log`   | Mounted from host in Docker     |

Log format: `YYYY-MM-DD HH:MM:SS,ms [LEVEL] module: message`

---

## 12. Backup & Data Retention

### PostgreSQL Backups

```bash
# Dump (from host, with Docker running)
docker compose exec db pg_dump -U valuesentinel valuesentinel > backup.sql

# Restore
cat backup.sql | docker compose exec -T db psql -U valuesentinel valuesentinel
```

### SQLite Backups

Simply copy `data/valuesentinel.db` while the application is stopped.

### Data Retention

Alert history accumulates over time. The dashboard displays the most recent 200 entries. To purge old history, connect to the database directly:

```sql
DELETE FROM alert_history WHERE triggered_at < NOW() - INTERVAL '90 days';
```

---

## 13. Updating / Upgrading

### Docker

```bash
git pull
docker compose down
docker compose build --no-cache
docker compose up -d
```

Alembic migrations run automatically on startup — new schema changes are applied on boot.

### Local

```bash
git pull
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
```

---

## 14. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `StringDataRightTruncation` on alert creation | Old DB schema with narrow VARCHAR columns | Run `alembic upgrade head` to apply migration 002 |
| `IBKR connection failed` warning | IBKR Gateway not running or not configured | Expected if not using IBKR — yfinance fallback is automatic |
| `egg_info error` during Docker build | Missing `src/` directory at build time | Ensure Dockerfile copies `src/` before `pip install` |
| `.env` changes not taking effect | Containers read env at startup | `docker compose down && docker compose up -d` |
| `No module named 'psycopg2'` | PostgreSQL driver not installed | `pip install ".[postgres]"` or use Docker |
| Dashboard shows 0 tickers | No tickers added yet | Add via dashboard "Manage Tickers" or CLI `add-ticker` |
| Notifications not received | Channel not configured or credentials wrong | Check Settings page; verify env vars; check logs for errors |
| yfinance rate limiting | Too many tickers with frequent checks | Increase `CHECK_INTERVAL_MINUTES` or reduce ticker count |
