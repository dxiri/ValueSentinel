"""Email notification dispatcher via SMTP."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from valuesentinel.config import get_config
from valuesentinel.logging_config import get_logger
from valuesentinel.models import AlertHistory
from valuesentinel.notifications.base import NotificationDispatcher

logger = get_logger("notifications.email")


class EmailDispatcher(NotificationDispatcher):
    """Send alert notifications via SMTP email."""

    def __init__(self) -> None:
        cfg = get_config().email
        self._host = cfg.host
        self._port = cfg.port
        self._username = cfg.username
        self._password = cfg.password
        self._from = cfg.from_address
        self._to = cfg.to_address

    @property
    def channel_name(self) -> str:
        return "email"

    def is_configured(self) -> bool:
        return bool(self._host and self._from and self._to)

    def send(self, history: AlertHistory) -> bool:
        if not self.is_configured():
            logger.warning("Email not configured, skipping")
            return False

        msg = self._build_message(history)

        for attempt in range(3):
            try:
                with smtplib.SMTP(self._host, self._port, timeout=15) as server:
                    server.ehlo()
                    if self._port != 25:
                        server.starttls()
                        server.ehlo()
                    if self._username and self._password:
                        server.login(self._username, self._password)
                    server.send_message(msg)
                logger.info("Email notification sent for alert %d", history.alert_id)
                return True
            except Exception as e:
                backoff = 5 * (3 ** attempt)
                logger.error("Email send failed (attempt %d): %s", attempt + 1, e)
                import time
                time.sleep(backoff)

        return False

    def _build_message(self, history: AlertHistory) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = f"🔔 ValueSentinel Alert — {history.message[:60]}"
        msg["From"] = self._from
        msg["To"] = self._to

        body_parts = [
            "ValueSentinel Alert",
            "=" * 40,
            "",
            history.message,
            "",
        ]
        if history.historical_min is not None:
            body_parts.append(
                f"Historical range: {history.historical_min:.2f} – {history.historical_max:.2f}"
            )
        if history.timeframe_years:
            body_parts.append(f"Timeframe: {history.timeframe_years:.1f} years")

        msg.set_content("\n".join(body_parts))
        return msg
