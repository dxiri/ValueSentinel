"""Telegram notification dispatcher via Bot API."""

from __future__ import annotations

import httpx

from valuesentinel.config import get_config
from valuesentinel.logging_config import get_logger
from valuesentinel.models import AlertHistory
from valuesentinel.notifications.base import NotificationDispatcher

logger = get_logger("notifications.telegram")


class TelegramDispatcher(NotificationDispatcher):
    """Send alert notifications via Telegram Bot API."""

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self) -> None:
        cfg = get_config().telegram
        self._token = cfg.bot_token
        self._chat_id = cfg.chat_id

    @property
    def channel_name(self) -> str:
        return "telegram"

    def is_configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, history: AlertHistory) -> bool:
        if not self.is_configured():
            logger.warning("Telegram not configured, skipping")
            return False

        url = self.BASE_URL.format(token=self._token)
        text = self._format_message(history)

        for attempt in range(3):
            try:
                resp = httpx.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    logger.info("Telegram notification sent for alert %d", history.alert_id)
                    return True
                elif resp.status_code == 429:
                    retry_after = resp.json().get("parameters", {}).get("retry_after", 60)
                    logger.warning("Telegram rate limit, retry after %ds", retry_after)
                    import time
                    time.sleep(retry_after)
                else:
                    logger.error("Telegram API error %d: %s", resp.status_code, resp.text)
            except httpx.HTTPError as e:
                backoff = 5 * (3 ** attempt)
                logger.error("Telegram send failed (attempt %d): %s", attempt + 1, e)
                import time
                time.sleep(backoff)

        return False

    def _format_message(self, history: AlertHistory) -> str:
        lines = [
            "<b>🔔 ValueSentinel Alert</b>",
            "",
            history.message,
        ]
        if history.historical_min is not None:
            lines.append(
                f"📊 Historical range: {history.historical_min:.2f} – {history.historical_max:.2f}"
            )
        return "\n".join(lines)
