"""Sentiment Advisor agent.

Lightweight news interpreter that augments the advisory crew's context
with qualitative sentiment insights when deterministic sentiment data
alone is insufficient.
"""

from __future__ import annotations

from crewai import Agent


def create_sentiment_advisor(
    agent_config: dict[str, str],
    verbose: bool = False,
) -> Agent:
    """Create the Sentiment Advisor agent.

    Args:
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Sentiment Advisor"),
        goal=agent_config.get("goal", "Interpret market sentiment and news"),
        backstory=agent_config.get("backstory", "Alternative data specialist"),
        tools=[],
        verbose=verbose,
    )
