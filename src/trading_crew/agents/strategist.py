"""Market Context Advisor agent.

Reviews deterministic pipeline output (market analyses, signals, risk results,
uncertainty factors) and recommends adjustments when market conditions warrant
human-like contextual reasoning.
"""

from __future__ import annotations

from crewai import Agent


def create_context_advisor(
    agent_config: dict[str, str],
    verbose: bool = False,
) -> Agent:
    """Create the Market Context Advisor agent.

    Args:
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Market Context Advisor"),
        goal=agent_config.get("goal", "Provide contextual trading advice"),
        backstory=agent_config.get("backstory", "Senior market analyst"),
        tools=[],
        verbose=verbose,
    )
