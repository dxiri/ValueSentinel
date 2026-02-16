"""Application configuration loaded from environment variables.

All env-var reads use ``field(default_factory=…)`` so that values are resolved
at **instantiation** time, not at module-import time.  This makes the config
classes work correctly with ``@patch.dict("os.environ", …)`` in tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    """Read an environment variable (helper for default_factory lambdas)."""
    return os.getenv(key, default)


def _env_int(key: str, default: int = 0) -> int:
    return int(os.getenv(key, str(default)))


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///data/valuesentinel.db"))


@dataclass(frozen=True)
class SchedulerConfig:
    check_interval_minutes: int = field(default_factory=lambda: _env_int("CHECK_INTERVAL_MINUTES", 15))


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass(frozen=True)
class DiscordConfig:
    webhook_url: str = field(default_factory=lambda: _env("DISCORD_WEBHOOK_URL"))

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)


@dataclass(frozen=True)
class EmailConfig:
    host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    port: int = field(default_factory=lambda: _env_int("SMTP_PORT", 587))
    username: str = field(default_factory=lambda: _env("SMTP_USERNAME"))
    password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    from_address: str = field(default_factory=lambda: _env("SMTP_FROM_ADDRESS"))
    to_address: str = field(default_factory=lambda: _env("SMTP_TO_ADDRESS"))

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.from_address and self.to_address)


@dataclass(frozen=True)
class PushoverConfig:
    user_key: str = field(default_factory=lambda: _env("PUSHOVER_USER_KEY"))
    api_token: str = field(default_factory=lambda: _env("PUSHOVER_API_TOKEN"))

    @property
    def enabled(self) -> bool:
        return bool(self.user_key and self.api_token)


@dataclass(frozen=True)
class IBKRConfig:
    host: str = field(default_factory=lambda: _env("IBKR_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("IBKR_PORT", 7497))
    client_id: int = field(default_factory=lambda: _env_int("IBKR_CLIENT_ID", 1))


@dataclass(frozen=True)
class LoggingConfig:
    level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    log_file: str = field(default_factory=lambda: _env("LOG_FILE", "logs/valuesentinel.log"))


@dataclass(frozen=True)
class AppConfig:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    pushover: PushoverConfig = field(default_factory=PushoverConfig)
    ibkr: IBKRConfig = field(default_factory=IBKRConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def get_config() -> AppConfig:
    """Return a fresh application configuration (reads env vars)."""
    return AppConfig()
