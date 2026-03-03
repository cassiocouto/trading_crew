"""Notification service for alerts and reports.

Supports Telegram (primary) and extensible to webhooks, email, etc.
Gracefully degrades when credentials are not configured.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    """Protocol for notification channels (Telegram, webhook, etc.)."""

    def send(self, message: str) -> bool:
        """Send a message. Returns True on success."""
        ...


class TelegramChannel:
    """Send messages via the Telegram Bot API.

    Args:
        bot_token: Telegram bot token from BotFather.
        chat_id: Target chat/group/channel ID.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._url = self.BASE_URL.format(token=bot_token)
        self._chat_id = chat_id

    def send(self, message: str) -> bool:
        """Send a Telegram message. Returns True on success."""
        try:
            response = httpx.post(
                self._url,
                json={"chat_id": self._chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=10.0,
            )
            if response.status_code == 200:
                return True
            logger.warning("Telegram API returned %d: %s", response.status_code, response.text)
            return False
        except httpx.HTTPError as e:
            logger.error("Failed to send Telegram message: %s", e)
            return False


class NotificationService:
    """Manages notification channels and message dispatch.

    Usage:
        service = NotificationService.from_settings()
        service.notify("Trade executed: BUY 0.01 BTC @ $60,000")
    """

    def __init__(self, channels: list[NotificationChannel] | None = None) -> None:
        self._channels: list[NotificationChannel] = channels or []

    @classmethod
    def from_settings(cls) -> NotificationService:
        """Create a NotificationService from application settings."""
        from trading_crew.config.settings import get_settings

        settings = get_settings()
        channels: list[NotificationChannel] = []

        if settings.telegram_enabled:
            channels.append(
                TelegramChannel(settings.telegram_bot_token, settings.telegram_chat_id)
            )
            logger.info("Telegram notifications enabled")
        else:
            logger.info("Telegram not configured — notifications disabled")

        return cls(channels)

    def notify(self, message: str) -> None:
        """Send a message to all configured channels.

        Failures on individual channels are logged but don't raise exceptions.
        """
        for channel in self._channels:
            try:
                channel.send(message)
            except Exception as e:
                logger.error("Notification channel failed: %s", e)

    def notify_trade(self, action: str, symbol: str, amount: float, price: float) -> None:
        """Send a formatted trade notification."""
        msg = f"*{action}* {amount:.6f} {symbol} @ {price:,.2f}"
        self.notify(msg)

    def notify_error(self, error: str) -> None:
        """Send an error alert."""
        self.notify(f"*ERROR*: {error}")

    @property
    def has_channels(self) -> bool:
        """Whether any notification channels are configured."""
        return len(self._channels) > 0
