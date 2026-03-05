"""Analyst Agent — technical analysis.

Computes technical indicators (EMA, RSI, Bollinger Bands, etc.) from
raw market data and produces structured MarketAnalysis objects.

Replaces: scattered indicator logic in silvia_v2's observer.py and behaviors.
"""

from __future__ import annotations

from crewai import Agent

from trading_crew.tools.technical_analysis import AnalyzeMarketTool


def create_analyst_agent(agent_config: dict[str, str], verbose: bool = False) -> Agent:
    """Create the Analyst Agent with technical analysis tools.

    Args:
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Technical Analyst"),
        goal=agent_config.get("goal", "Compute indicators and identify trends"),
        backstory=agent_config.get("backstory", "Quantitative analysis expert"),
        tools=[AnalyzeMarketTool()],
        verbose=verbose,
    )
