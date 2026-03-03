"""Sentiment Agent — market sentiment analysis.

Gathers sentiment data from external sources (Fear & Greed Index, news,
social media) and produces a sentiment score. This is a Phase 2b agent
and uses a placeholder implementation in Phase 1.
"""

from __future__ import annotations

from crewai import Agent


def create_sentiment_agent(agent_config: dict[str, str]) -> Agent:
    """Create the Sentiment Agent.

    Note: In Phase 1, this agent has no external tools. Sentiment tools
    will be added in Phase 2b when the sentiment_tool.py is implemented.

    Args:
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Market Sentiment Analyst"),
        goal=agent_config.get("goal", "Assess market sentiment"),
        backstory=agent_config.get("backstory", "Alternative data specialist"),
        tools=[],
        verbose=True,
    )
