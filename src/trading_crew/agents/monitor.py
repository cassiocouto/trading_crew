"""Monitor Agent — order lifecycle tracking.

Tracks open orders, detects fills, cancels stale orders, and keeps
portfolio state synchronized with exchange reality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crewai import Agent

from trading_crew.tools.database_tool import GetOpenOrdersTool, UpdateOrderStatusTool
from trading_crew.tools.exchange_tool import CancelOrderTool, FetchOrderStatusTool
from trading_crew.tools.notification_tool import SendNotificationTool

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService
    from trading_crew.services.exchange_service import ExchangeService
    from trading_crew.services.notification_service import NotificationService


def create_monitor_agent(
    notification_service: NotificationService,
    agent_config: dict[str, str],
    exchange_service: ExchangeService | None = None,
    db_service: DatabaseService | None = None,
) -> Agent:
    """Create the Monitor Agent with order-polling and lifecycle tools.

    Args:
        notification_service: For fill and cancellation notifications.
        agent_config: Agent role/goal/backstory from agents.yaml.
        exchange_service: CCXT exchange facade for status polling and cancellation.
        db_service: Database service for querying and updating order records.

    Returns:
        A configured CrewAI Agent.
    """
    tools = [SendNotificationTool(notification_service=notification_service)]

    if exchange_service is not None:
        tools.append(FetchOrderStatusTool(exchange_service=exchange_service))
        tools.append(CancelOrderTool(exchange_service=exchange_service))

    if db_service is not None:
        tools.append(GetOpenOrdersTool(db_service=db_service))
        tools.append(UpdateOrderStatusTool(db_service=db_service))

    return Agent(
        role=agent_config.get("role", "Order Monitor"),
        goal=agent_config.get("goal", "Track and manage open orders"),
        backstory=agent_config.get("backstory", "Post-trade operations specialist"),
        tools=tools,
        verbose=True,
    )
