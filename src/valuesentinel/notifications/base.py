"""Base notification dispatcher interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from valuesentinel.models import AlertHistory


class NotificationDispatcher(ABC):
    """Abstract base for notification channel dispatchers."""

    @abstractmethod
    def send(self, history: AlertHistory) -> bool:
        """Send a notification for a triggered alert.

        Returns True if delivery succeeded, False otherwise.
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this channel has valid configuration."""
        ...

    @property
    @abstractmethod
    def channel_name(self) -> str:
        ...
