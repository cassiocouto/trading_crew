"""Sentinel Agent — multi-exchange price feed.

Responsible for fetching real-time market data (tickers, OHLCV candles,
order books) from configured exchanges via CCXT. This agent is the data
foundation that all other agents depend on.

Replaces: novadax_ws_observer.py and novadax_api_service.py from silvia_v2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crewai import Agent

from trading_crew.tools.database_tool import SaveOHLCVBatchTool, SaveTickerTool
from trading_crew.tools.exchange_tool import FetchOHLCVTool, FetchTickerTool

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService
    from trading_crew.services.exchange_service import ExchangeService


def create_sentinel_agent(
    exchange_service: ExchangeService,
    db_service: DatabaseService,
    agent_config: dict[str, str],
) -> Agent:
    """Create the Sentinel Agent with exchange and database tools.

    Args:
        exchange_service: CCXT exchange facade.
        db_service: Database service for persisting data.
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Market Data Sentinel"),
        goal=agent_config.get("goal", "Fetch accurate market data"),
        backstory=agent_config.get("backstory", "Expert data specialist"),
        tools=[
            FetchTickerTool(exchange_service=exchange_service),
            FetchOHLCVTool(exchange_service=exchange_service),
            SaveTickerTool(db_service=db_service),
            SaveOHLCVBatchTool(db_service=db_service),
        ],
        verbose=True,
    )
