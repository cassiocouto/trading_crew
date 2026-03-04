"""CrewAI Tool for risk validation.

Wraps the RiskPipeline service so the Risk Manager agent can trigger
deterministic risk evaluation from within a CrewAI task.
"""

from __future__ import annotations

import json
import logging

from crewai.tools import BaseTool
from pydantic import Field

from trading_crew.models.portfolio import Portfolio
from trading_crew.services.risk_pipeline import RiskPipeline

logger = logging.getLogger(__name__)


class EvaluateRiskTool(BaseTool):
    """Evaluate a trade signal against the risk pipeline."""

    name: str = "evaluate_risk"
    description: str = (
        "Validate a trade signal against the portfolio risk pipeline. "
        "Input: JSON with 'symbol', 'exchange', 'signal_type' (buy/sell), "
        "'confidence' (0-1), 'entry_price', and 'strategy_name'. "
        "Returns the risk verdict, approved amount, stop-loss, and reasons."
    )
    risk_pipeline: RiskPipeline = Field(exclude=True)
    portfolio: Portfolio = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        from trading_crew.models.signal import (
            SignalStrength,
            SignalType,
            TradeSignal,
        )

        try:
            params = json.loads(input_str)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON input: {e}"})

        required = ("symbol", "signal_type", "entry_price")
        missing = [k for k in required if k not in params]
        if missing:
            return json.dumps({"error": f"Missing required keys: {', '.join(missing)}"})

        try:
            confidence = float(params.get("confidence", 0.5))
            signal = TradeSignal(
                symbol=params["symbol"],
                exchange=params.get("exchange", "unknown"),
                signal_type=SignalType(params["signal_type"]),
                strength=SignalStrength(params.get("strength", "moderate")),
                confidence=confidence,
                strategy_name=params.get("strategy_name", "unknown"),
                entry_price=float(params["entry_price"]),
                stop_loss_price=(
                    float(params["stop_loss_price"]) if params.get("stop_loss_price") else None
                ),
                reason=params.get("reason", ""),
            )
        except (ValueError, KeyError) as e:
            return json.dumps({"error": f"Invalid signal parameters: {e}"})

        result = self.risk_pipeline.evaluate(signal, self.portfolio)

        return json.dumps(
            {
                "verdict": result.verdict.value,
                "is_approved": result.is_approved,
                "approved_amount": round(result.approved_amount, 8),
                "approved_price": result.approved_price,
                "stop_loss_price": result.stop_loss_price,
                "take_profit_price": result.take_profit_price,
                "checks_passed": result.checks_passed,
                "checks_failed": result.checks_failed,
                "reasons": result.reasons,
            },
            indent=2,
        )
