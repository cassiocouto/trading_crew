"""Executor Agent — order placement.

Places orders on the exchange (or simulates them in paper-trading mode).
Handles precision formatting, minimum order sizes, and error recovery.
"""

from __future__ import annotations

from crewai import Agent

from trading_crew.tools.exchange_tool import PlaceOrderTool
from trading_crew.tools.notification_tool import SendNotificationTool
from trading_crew.services.exchange_service import ExchangeService
from trading_crew.services.notification_service import NotificationService


def create_executor_agent(
    exchange_service: ExchangeService,
    notification_service: NotificationService,
    agent_config: dict[str, str],
) -> Agent:
    """Create the Executor Agent with order placement tools.

    Args:
        exchange_service: CCXT exchange facade.
        notification_service: For trade notifications.
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Order Executor"),
        goal=agent_config.get("goal", "Place orders reliably"),
        backstory=agent_config.get("backstory", "Execution specialist"),
        tools=[
            PlaceOrderTool(exchange_service=exchange_service),
            SendNotificationTool(notification_service=notification_service),
        ],
        verbose=True,
    )
