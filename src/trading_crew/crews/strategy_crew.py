"""Strategy Crew.

Evaluates market analysis to generate trade signals and validates them
through risk management. Runs after the Market Intelligence Crew.

Agents:
  - Strategist: Runs strategies and generates signals
  - Risk Manager: Validates signals against risk limits

Tasks (sequential):
  1. generate_signals → Strategist
  2. validate_risk → Risk Manager (depends on step 1)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crewai import Agent, Crew, Task

if TYPE_CHECKING:
    from trading_crew.models.risk import RiskParams


class StrategyCrew:
    """Assembles and runs the Strategy Crew.

    Args:
        strategist: The Strategist agent instance.
        risk_manager: The Risk Manager agent instance.
        task_configs: Task definitions from tasks.yaml.
        risk_params: Risk management parameters.
    """

    def __init__(
        self,
        strategist: Agent,
        risk_manager: Agent,
        task_configs: dict[str, dict[str, str]],
        risk_params: RiskParams,
    ) -> None:
        self._strategist = strategist
        self._risk_manager = risk_manager
        self._task_configs = task_configs
        self._risk_params = risk_params

    def build(self) -> Crew:
        """Build the Crew with its agents and tasks."""
        signal_config = self._task_configs.get("generate_signals", {})
        risk_config = self._task_configs.get("validate_risk", {})

        rp = self._risk_params

        signal_task = Task(
            description=signal_config.get("description", "Generate trade signals").format(
                min_confidence=rp.min_confidence,
            ),
            expected_output=signal_config.get("expected_output", "Trade signals"),
            agent=self._strategist,
        )

        risk_task = Task(
            description=risk_config.get("description", "Validate risk").format(
                max_position_size_pct=rp.max_position_size_pct,
                max_portfolio_exposure_pct=rp.max_portfolio_exposure_pct,
                max_drawdown_pct=rp.max_drawdown_pct,
                risk_per_trade_pct=rp.risk_per_trade_pct,
                default_stop_loss_pct=rp.default_stop_loss_pct,
            ),
            expected_output=risk_config.get("expected_output", "Risk check results"),
            agent=self._risk_manager,
            context=[signal_task],
        )

        return Crew(
            agents=[self._strategist, self._risk_manager],
            tasks=[signal_task, risk_task],
            verbose=True,
        )
