# ValueSentinel

**Financial valuation metrics alerter for value investors.**

ValueSentinel monitors fundamental valuation ratios — P/E, EV/EBITDA, P/B, P/FCF, and more — and sends alerts when user-defined conditions are met. Unlike traditional price-alert tools, ValueSentinel alerts on *value* (e.g., "P/E dropped below 15x" or "EV/EBITDA hit a 10-year low").

## Features

- **9 valuation metrics** — Trailing P/E, Forward P/E, EV/EBITDA, EV/EBIT, P/FCF, P/FFO, P/AFFO, P/B, P/S
- **3 alert types** — Absolute threshold, percentage change, historical extremes (rolling window)
- **Global equities** — Any ticker supported by yfinance (US, Europe, Asia-Pacific, Emerging Markets)
- **4 notification channels** — Telegram, Discord, Email (SMTP), Pushover
- **Priority levels** — Critical (immediate), Normal (next cycle), Informational (log only)
- **Configurable cooldowns** — 1h, 6h, 12h, 24h, 48h, or 1 week per alert
- **Streamlit dashboard** — Create, edit, pause, resume, stop, and remove alerts; view history; manage watchlist
- **Optional IBKR integration** — Real-time pricing via Interactive Brokers; auto-fallback to yfinance delayed quotes
- **Docker-ready** — Single `docker compose up` for production deployment with PostgreSQL

## Quick Start

### Prerequisites

- Python 3.10+
- (Optional) Docker & Docker Compose for containerized deployment

### Local Development

```bash
# Clone the repo
git clone https://github.com/<your-username>/ValueSentinel.git
cd ValueSentinel

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys / notification credentials

# Initialize the database
valuesentinel init-db

# Run the dashboard
streamlit run src/valuesentinel/dashboard/app.py
```

### Docker (Recommended for Production)

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL and notification credentials

docker compose up -d
```

The dashboard will be available at **http://localhost:8501**.

Three services start automatically:
- **app** — Streamlit dashboard
- **scheduler** — Background alert check loop
- **db** — PostgreSQL 16

## CLI

```bash
valuesentinel init-db          # Initialize database tables
valuesentinel add-ticker AAPL  # Add a ticker to watchlist
valuesentinel add-ticker SHEL.L  # Non-US ticker (London)
valuesentinel refresh AAPL     # Refresh fundamentals for a ticker
valuesentinel check            # Run one alert-check cycle
valuesentinel run              # Start the scheduler loop
```

## Project Structure

```
ValueSentinel/
├── src/valuesentinel/
│   ├── models.py              # SQLAlchemy models & enums
│   ├── config.py              # Environment-based configuration
│   ├── cli.py                 # CLI entry point
│   ├── data/
│   │   ├── yfinance_connector.py   # yfinance data fetching & caching
│   │   └── price_provider.py       # IBKR / yfinance price abstraction
│   ├── calculator/
│   │   └── valuation.py       # All 9 valuation metric formulas
│   ├── alerts/
│   │   └── engine.py          # Alert evaluation & state management
│   ├── notifications/
│   │   ├── manager.py         # Multi-channel dispatch
│   │   ├── telegram.py        # Telegram Bot API
│   │   ├── discord.py         # Discord Webhooks
│   │   ├── email_notifier.py  # SMTP
│   │   └── pushover.py        # Pushover API
│   ├── scheduler/
│   │   └── jobs.py            # APScheduler job definitions
│   └── dashboard/
│       └── app.py             # Streamlit UI (5 pages)
├── alembic/                   # Database migrations
├── tests/                     # pytest test suite
├── docs/
│   ├── deployment-guide.md    # Technical deployment documentation
│   └── user-guide.md          # End-user guide
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
├── .env.example
└── README.md
```

## Configuration

Copy `.env.example` to `.env` and fill in the values you need. At minimum:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | SQLite or PostgreSQL connection string |
| `CHECK_INTERVAL_MINUTES` | No | Check cycle interval (default: 15) |
| `TELEGRAM_BOT_TOKEN` | If using Telegram | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | If using Telegram | Target chat/group ID |
| `DISCORD_WEBHOOK_URL` | If using Discord | Webhook URL |
| `SMTP_HOST` / `SMTP_PORT` / etc. | If using Email | SMTP server details |
| `PUSHOVER_USER_KEY` / `PUSHOVER_API_TOKEN` | If using Pushover | Pushover credentials |
| `IBKR_HOST` / `IBKR_PORT` | If using IBKR | IB Gateway/TWS connection |

See [docs/deployment-guide.md](docs/deployment-guide.md) for full configuration reference.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=valuesentinel --cov-report=term-missing

# Lint
ruff check src/ tests/

# Type check
mypy src/valuesentinel/
```

## Documentation

- [Deployment Guide](docs/deployment-guide.md) — Installation, Docker, migrations, monitoring, backups
- [User Guide](docs/user-guide.md) — Dashboard usage, alert creation, metrics reference, FAQ

## License

MIT
