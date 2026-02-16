"""Tests for notification dispatchers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from valuesentinel.models import AlertHistory, DeliveryStatus
from valuesentinel.notifications.telegram import TelegramDispatcher
from valuesentinel.notifications.discord import DiscordDispatcher
from valuesentinel.notifications.email_notifier import EmailDispatcher
from valuesentinel.notifications.pushover import PushoverDispatcher
from valuesentinel.notifications.manager import NotificationManager


def _make_history() -> AlertHistory:
    """Create a mock AlertHistory for testing."""
    return AlertHistory(
        id=1,
        alert_id=1,
        triggered_at=datetime.now(timezone.utc),
        metric_value=23.36,
        threshold_value=25.0,
        historical_min=20.0,
        historical_max=45.0,
        timeframe_years=10.0,
        message="AAPL P/E (Trailing) = 23.36 (below threshold 25.00)\nCalculated against 10.0 years of data. Currency: USD.",
        delivery_status=DeliveryStatus.PENDING,
        delivery_channels="telegram,discord",
    )


class TestTelegramDispatcher:
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""})
    def test_not_configured(self):
        dispatcher = TelegramDispatcher()
        assert not dispatcher.is_configured()

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "fake:token", "TELEGRAM_CHAT_ID": "12345"})
    def test_configured(self):
        dispatcher = TelegramDispatcher()
        assert dispatcher.is_configured()
        assert dispatcher.channel_name == "telegram"

    @patch("valuesentinel.notifications.telegram.httpx.post")
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "fake:token", "TELEGRAM_CHAT_ID": "12345"})
    def test_send_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        dispatcher = TelegramDispatcher()
        history = _make_history()
        assert dispatcher.send(history) is True
        mock_post.assert_called_once()


class TestDiscordDispatcher:
    @patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": ""})
    def test_not_configured(self):
        dispatcher = DiscordDispatcher()
        assert not dispatcher.is_configured()

    @patch("valuesentinel.notifications.discord.httpx.post")
    @patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/fake"})
    def test_send_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_post.return_value = mock_resp

        dispatcher = DiscordDispatcher()
        history = _make_history()
        assert dispatcher.send(history) is True


class TestEmailDispatcher:
    @patch.dict("os.environ", {"SMTP_HOST": "", "SMTP_FROM_ADDRESS": "", "SMTP_TO_ADDRESS": ""})
    def test_not_configured(self):
        dispatcher = EmailDispatcher()
        assert not dispatcher.is_configured()

    @patch.dict("os.environ", {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "user",
        "SMTP_PASSWORD": "pass",
        "SMTP_FROM_ADDRESS": "from@example.com",
        "SMTP_TO_ADDRESS": "to@example.com",
    })
    def test_configured(self):
        dispatcher = EmailDispatcher()
        assert dispatcher.is_configured()
        assert dispatcher.channel_name == "email"


class TestPushoverDispatcher:
    @patch.dict("os.environ", {"PUSHOVER_USER_KEY": "", "PUSHOVER_API_TOKEN": ""})
    def test_not_configured(self):
        dispatcher = PushoverDispatcher()
        assert not dispatcher.is_configured()

    @patch.dict("os.environ", {"PUSHOVER_USER_KEY": "uFakeKey123", "PUSHOVER_API_TOKEN": "aFakeToken456"})
    def test_configured(self):
        dispatcher = PushoverDispatcher()
        assert dispatcher.is_configured()
        assert dispatcher.channel_name == "pushover"

    @patch("valuesentinel.notifications.pushover.httpx.post")
    @patch.dict("os.environ", {"PUSHOVER_USER_KEY": "uFakeKey123", "PUSHOVER_API_TOKEN": "aFakeToken456"})
    def test_send_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": 1, "request": "abc123"}
        mock_post.return_value = mock_resp

        dispatcher = PushoverDispatcher()
        history = _make_history()
        assert dispatcher.send(history) is True
        mock_post.assert_called_once()
