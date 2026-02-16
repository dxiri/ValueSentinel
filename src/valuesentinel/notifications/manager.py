"""Notification dispatcher manager — routes alerts to configured channels."""

from __future__ import annotations

from sqlalchemy.orm import Session

from valuesentinel.logging_config import get_logger
from valuesentinel.models import AlertHistory, DeliveryStatus
from valuesentinel.notifications.base import NotificationDispatcher
from valuesentinel.notifications.discord import DiscordDispatcher
from valuesentinel.notifications.email_notifier import EmailDispatcher
from valuesentinel.notifications.pushover import PushoverDispatcher
from valuesentinel.notifications.telegram import TelegramDispatcher

logger = get_logger("notifications.manager")


class NotificationManager:
    """Routes alert history events to the appropriate notification channels."""

    def __init__(self) -> None:
        self._dispatchers: dict[str, NotificationDispatcher] = {}
        for cls in (TelegramDispatcher, DiscordDispatcher, EmailDispatcher, PushoverDispatcher):
            dispatcher = cls()
            if dispatcher.is_configured():
                self._dispatchers[dispatcher.channel_name] = dispatcher
                logger.info("Notification channel enabled: %s", dispatcher.channel_name)

    def dispatch(self, session: Session, history: AlertHistory) -> bool:
        """Send notifications for a triggered alert to all requested channels.

        Returns True if at least one channel succeeded.
        """
        from valuesentinel.models import Alert, AlertPriority

        alert = session.get(Alert, history.alert_id)
        if alert is None:
            return False

        # Informational priority: no push notifications
        if alert.priority == AlertPriority.INFORMATIONAL:
            history.delivery_status = DeliveryStatus.DELIVERED
            history.delivery_channels = "dashboard_only"
            logger.info("Informational alert %d logged (no push)", alert.id)
            return True

        requested_channels = (history.delivery_channels or "").split(",")
        succeeded: list[str] = []
        failed: list[str] = []

        for channel_name in requested_channels:
            channel_name = channel_name.strip()
            dispatcher = self._dispatchers.get(channel_name)
            if dispatcher is None:
                logger.debug("Channel %s not configured, skipping", channel_name)
                continue

            if dispatcher.send(history):
                succeeded.append(channel_name)
            else:
                failed.append(channel_name)

        if succeeded:
            history.delivery_status = DeliveryStatus.DELIVERED
            history.delivery_channels = ",".join(succeeded)
            return True
        else:
            history.delivery_status = DeliveryStatus.FAILED
            logger.warning(
                "All notification channels failed for alert %d: %s",
                alert.id,
                failed,
            )
            return False
