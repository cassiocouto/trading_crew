"""Risk Manager Agent — validates signals against risk limits.

The most critical agent in the system. No trade signal reaches execution
without passing through the Risk Manager's validation pipeline.
"""

from __future__ import annotations

from crewai import Agent


def create_risk_manager_agent(agent_config: dict[str, str]) -> Agent:
    """Create the Risk Manager Agent.

    The Risk Manager evaluates each trade signal against portfolio limits,
    calculates position sizes, and sets stop-losses.

    Args:
        agent_config: Agent role/goal/backstory from agents.yaml.

    Returns:
        A configured CrewAI Agent.
    """
    return Agent(
        role=agent_config.get("role", "Risk Manager"),
        goal=agent_config.get("goal", "Protect capital through risk validation"),
        backstory=agent_config.get("backstory", "Conservative risk professional"),
        tools=[],
        verbose=True,
    )
