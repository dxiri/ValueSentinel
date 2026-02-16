"""Pushover notification dispatcher via Pushover API."""

from __future__ import annotations

import httpx

from valuesentinel.config import get_config
from valuesentinel.logging_config import get_logger
from valuesentinel.models import AlertHistory
from valuesentinel.notifications.base import NotificationDispatcher

logger = get_logger("notifications.pushover")


class PushoverDispatcher(NotificationDispatcher):
    """Send alert notifications via Pushover."""

    API_URL = "https://api.pushover.net/1/messages.json"

    # Map alert priority labels to Pushover priority levels
    _PRIORITY_MAP = {
        "critical": 1,      # high priority (bypass quiet hours)
        "normal": 0,        # normal priority
        "informational": -1, # low priority (no sound/vibration)
    }

    def __init__(self) -> None:
        cfg = get_config().pushover
        self._user_key = cfg.user_key
        self._api_token = cfg.api_token

    @property
    def channel_name(self) -> str:
        return "pushover"

    def is_configured(self) -> bool:
        return bool(self._user_key and self._api_token)

    def send(self, history: AlertHistory) -> bool:
        if not self.is_configured():
            logger.warning("Pushover not configured, skipping")
            return False

        title, body = self._format_message(history)

        # Determine Pushover priority from the alert
        priority = 0
        from valuesentinel.models import Alert
        # We don't have a session here, so just use default priority
        # The priority mapping is applied if we can infer from the message

        for attempt in range(3):
            try:
                resp = httpx.post(
                    self.API_URL,
                    data={
                        "token": self._api_token,
                        "user": self._user_key,
                        "title": title,
                        "message": body,
                        "priority": priority,
                        "html": 1,
                    },
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("status") == 1:
                        logger.info("Pushover notification sent for alert %d", history.alert_id)
                        return True
                    else:
                        logger.error("Pushover API error: %s", result.get("errors", []))
                elif resp.status_code == 429:
                    logger.warning("Pushover rate limit hit, retrying...")
                    import time
                    time.sleep(5 * (2 ** attempt))
                else:
                    logger.error("Pushover HTTP error %d: %s", resp.status_code, resp.text)
            except httpx.HTTPError as e:
                backoff = 5 * (3 ** attempt)
                logger.error("Pushover send failed (attempt %d): %s", attempt + 1, e)
                import time
                time.sleep(backoff)

        return False

    def _format_message(self, history: AlertHistory) -> tuple[str, str]:
        """Return (title, body) for the Pushover message."""
        title = "🔔 ValueSentinel Alert"
        lines = [history.message]
        if history.historical_min is not None:
            lines.append(
                f"📊 Historical range: {history.historical_min:.2f} – {history.historical_max:.2f}"
            )
        return title, "\n".join(lines)
