"""CrewAI Tool for running trading strategies.

Wraps the StrategyRunner service so the Strategist agent can trigger
deterministic strategy evaluation from within a CrewAI task.
"""

from __future__ import annotations

import json
import logging

from crewai.tools import BaseTool
from pydantic import Field

from trading_crew.services.strategy_runner import StrategyRunner

logger = logging.getLogger(__name__)


class RunStrategiesTool(BaseTool):
    """Run trading strategies against market analyses and produce signals."""

    name: str = "run_strategies"
    description: str = (
        "Run all registered trading strategies against market analysis data. "
        "Input: JSON with 'analyses' — a dict keyed by symbol, each containing "
        "'current_price' and 'indicators' (dict of indicator name to value). "
        "Returns a list of trade signals with confidence scores."
    )
    strategy_runner: StrategyRunner = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        from datetime import UTC, datetime

        from trading_crew.models.market import MarketAnalysis
        from trading_crew.utils.datetime import parse_iso_utc

        try:
            params = json.loads(input_str)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON input: {e}"})

        raw_analyses = params.get("analyses", {})
        if not raw_analyses:
            return json.dumps({"error": "No analyses provided"})

        analyses: dict[str, MarketAnalysis] = {}
        for symbol, data in raw_analyses.items():
            try:
                raw_ts = data.get("timestamp")
                timestamp = parse_iso_utc(raw_ts) if raw_ts else datetime.now(UTC)
                analyses[symbol] = MarketAnalysis(
                    symbol=symbol,
                    exchange=data.get("exchange", "unknown"),
                    timestamp=timestamp,
                    current_price=float(data["current_price"]),
                    indicators={k: float(v) for k, v in data.get("indicators", {}).items()},
                )
            except (KeyError, ValueError, TypeError) as e:
                logger.warning("Skipping %s: invalid analysis data: %s", symbol, e)
                continue

        if not analyses:
            return json.dumps({"error": "No valid analyses could be parsed"})

        signals = self.strategy_runner.evaluate(analyses)

        return json.dumps(
            [
                {
                    "symbol": s.symbol,
                    "exchange": s.exchange,
                    "signal_type": s.signal_type.value,
                    "strength": s.strength.value,
                    "confidence": round(s.confidence, 4),
                    "strategy_name": s.strategy_name,
                    "entry_price": s.entry_price,
                    "reason": s.reason,
                }
                for s in signals
            ],
            indent=2,
        )
