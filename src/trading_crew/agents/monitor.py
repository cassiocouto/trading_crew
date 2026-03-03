"""Monitor Agent — order lifecycle tracking.

Tracks open orders, detects fills, cancels stale orders, and keeps
portfolio state synchronized with exchange reality.
"""

from __future__ import annotations

from crewai import Agent

from trading_crew.tools.notification_tool import SendNotificationTool
from trading_crew.services.notification_service import NotificationService


def create_monitor_agent(
    notification_service: NotificationService,
    agent_config: dict[str, str],
) -> Agent:
    """Create the Monitor Agent.

    Args:
        notification_service: For fill and cancellation notifications.
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Order Monitor"),
        goal=agent_config.get("goal", "Track and manage open orders"),
        backstory=agent_config.get("backstory", "Post-trade operations specialist"),
        tools=[
            SendNotificationTool(notification_service=notification_service),
        ],
        verbose=True,
    )
