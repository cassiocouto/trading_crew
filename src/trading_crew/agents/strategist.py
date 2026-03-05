"""Strategist Agent — signal generation.

Evaluates market analysis data through the configured trading strategies
and produces trade signals with confidence scores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crewai import Agent

if TYPE_CHECKING:
    from trading_crew.services.strategy_runner import StrategyRunner


def create_strategist_agent(
    agent_config: dict[str, str],
    strategy_runner: StrategyRunner | None = None,
    verbose: bool = False,
) -> Agent:
    """Create the Strategist Agent.

    Args:
        agent_config: Agent role/goal/backstory from agents.yaml.
        strategy_runner: Optional StrategyRunner service. When provided,
            a RunStrategiesTool is attached so the agent can trigger
            deterministic strategy evaluation.

    Returns:
        A configured CrewAI Agent.
    """
    tools: list[object] = []
    if strategy_runner is not None:
        from trading_crew.tools.strategy_tool import RunStrategiesTool

        tools.append(RunStrategiesTool(strategy_runner=strategy_runner))

    return Agent(
        role=agent_config.get("role", "Trading Strategist"),
        goal=agent_config.get("goal", "Generate trade signals"),
        backstory=agent_config.get("backstory", "Systematic trader"),
        tools=tools,
        verbose=verbose,
    )
