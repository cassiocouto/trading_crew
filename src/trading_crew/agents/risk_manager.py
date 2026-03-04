"""Risk Manager Agent — validates signals against risk limits.

The most critical agent in the system. No trade signal reaches execution
without passing through the Risk Manager's validation pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crewai import Agent

if TYPE_CHECKING:
    from trading_crew.models.portfolio import Portfolio
    from trading_crew.services.risk_pipeline import RiskPipeline


def create_risk_manager_agent(
    agent_config: dict[str, str],
    risk_pipeline: RiskPipeline | None = None,
    portfolio: Portfolio | None = None,
) -> Agent:
    """Create the Risk Manager Agent.

    Args:
        agent_config: Agent role/goal/backstory from agents.yaml.
        risk_pipeline: Optional RiskPipeline service. When provided along
            with a portfolio, an EvaluateRiskTool is attached so the agent
            can trigger deterministic risk validation.
        portfolio: Current portfolio state, required when risk_pipeline
            is provided.

    Returns:
        A configured CrewAI Agent.
    """
    tools: list[object] = []
    if risk_pipeline is not None and portfolio is not None:
        from trading_crew.tools.risk_tool import EvaluateRiskTool

        tools.append(EvaluateRiskTool(risk_pipeline=risk_pipeline, portfolio=portfolio))

    return Agent(
        role=agent_config.get("role", "Risk Manager"),
        goal=agent_config.get("goal", "Protect capital through risk validation"),
        backstory=agent_config.get("backstory", "Conservative risk professional"),
        tools=tools,
        verbose=True,
    )
