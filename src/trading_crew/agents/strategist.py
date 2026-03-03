"""Strategist Agent — signal generation.

Evaluates market analysis data through the configured trading strategies
and produces trade signals with confidence scores.
"""

from __future__ import annotations

from crewai import Agent


def create_strategist_agent(agent_config: dict[str, str]) -> Agent:
    """Create the Strategist Agent.

    The Strategist uses the LLM to interpret market analysis and strategy
    outputs, deciding whether to generate buy/sell/hold signals.

    Args:
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Trading Strategist"),
        goal=agent_config.get("goal", "Generate trade signals"),
        backstory=agent_config.get("backstory", "Systematic trader"),
        tools=[],
        verbose=True,
    )
