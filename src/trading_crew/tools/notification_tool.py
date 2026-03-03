"""CrewAI Tool for sending notifications."""

from __future__ import annotations

from crewai.tools import BaseTool
from pydantic import Field

from trading_crew.services.notification_service import NotificationService


class SendNotificationTool(BaseTool):
    """Send a notification message via configured channels (Telegram, etc.)."""

    name: str = "send_notification"
    description: str = (
        "Send a notification message to the configured channels (e.g. Telegram). "
        "Input: the message text to send."
    )
    notification_service: NotificationService = Field(exclude=True)

    def _run(self, message: str) -> str:
        self.notification_service.notify(message)
        return f"Notification sent: {message[:100]}"
