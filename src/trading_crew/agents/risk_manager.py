"""Risk Advisor agent.

Reviews deterministic risk pipeline output and recommends adjustments
(vetoes, tighter stops, position reductions) when uncertainty is high.
"""

from __future__ import annotations

from crewai import Agent


def create_risk_advisor(
    agent_config: dict[str, str],
    verbose: bool = False,
) -> Agent:
    """Create the Risk Advisor agent.

    Args:
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Risk Advisor"),
        goal=agent_config.get("goal", "Protect capital through advisory review"),
        backstory=agent_config.get("backstory", "Conservative risk professional"),
        tools=[],
        verbose=verbose,
    )
