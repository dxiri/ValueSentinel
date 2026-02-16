"""Discord notification dispatcher via Webhook."""

from __future__ import annotations

import httpx

from valuesentinel.config import get_config
from valuesentinel.logging_config import get_logger
from valuesentinel.models import AlertHistory
from valuesentinel.notifications.base import NotificationDispatcher

logger = get_logger("notifications.discord")


class DiscordDispatcher(NotificationDispatcher):
    """Send alert notifications via Discord Webhook."""

    def __init__(self) -> None:
        cfg = get_config().discord
        self._webhook_url = cfg.webhook_url

    @property
    def channel_name(self) -> str:
        return "discord"

    def is_configured(self) -> bool:
        return bool(self._webhook_url)

    def send(self, history: AlertHistory) -> bool:
        if not self.is_configured():
            logger.warning("Discord not configured, skipping")
            return False

        payload = self._build_payload(history)

        for attempt in range(3):
            try:
                resp = httpx.post(
                    self._webhook_url,
                    json=payload,
                    timeout=10.0,
                )
                if resp.status_code in (200, 204):
                    logger.info("Discord notification sent for alert %d", history.alert_id)
                    return True
                elif resp.status_code == 429:
                    retry_after = resp.json().get("retry_after", 60)
                    logger.warning("Discord rate limit, retry after %ds", retry_after)
                    import time
                    time.sleep(retry_after)
                else:
                    logger.error("Discord API error %d: %s", resp.status_code, resp.text)
            except httpx.HTTPError as e:
                backoff = 5 * (3 ** attempt)
                logger.error("Discord send failed (attempt %d): %s", attempt + 1, e)
                import time
                time.sleep(backoff)

        return False

    def _build_payload(self, history: AlertHistory) -> dict:
        description = history.message
        if history.historical_min is not None:
            description += (
                f"\n📊 Historical range: {history.historical_min:.2f} – "
                f"{history.historical_max:.2f}"
            )

        return {
            "embeds": [
                {
                    "title": "🔔 ValueSentinel Alert",
                    "description": description,
                    "color": 0xFF4444,  # red
                }
            ]
        }
