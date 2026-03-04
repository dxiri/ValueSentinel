"""Structured logging setup for ValueSentinel."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from valuesentinel.config import get_config


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON."""

    SENSITIVE_KEYS = {"token", "password", "secret", "webhook", "api_key", "bot_token"}

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_data["exception"] = self.formatException(record.exc_info)
        # Sanitize sensitive values
        msg = log_data["message"]
        for key in self.SENSITIVE_KEYS:
            if key in msg.lower():
                log_data["message"] = "[REDACTED — contains sensitive data]"
                break
        return json.dumps(log_data)


def setup_logging() -> None:
    """Configure application-wide logging with rotation and JSON output."""
    cfg = get_config().logging

    # Ensure log directory exists
    log_path = Path(cfg.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("valuesentinel")
    root_logger.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))

    # File handler with rotation (10MB, keep 5)
    file_handler = logging.handlers.RotatingFileHandler(
        cfg.log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setFormatter(JSONFormatter())

    # Console handler (human-readable, with redaction)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JSONFormatter())

    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a namespaced logger."""
    return logging.getLogger(f"valuesentinel.{name}")
