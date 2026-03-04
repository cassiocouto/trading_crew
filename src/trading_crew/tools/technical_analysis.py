"""CrewAI Tool for computing technical indicators.

Uses pandas and basic math to compute indicators. In Phase 2, this will
be enhanced with pandas-ta for the full indicator library.
"""

from __future__ import annotations

import json

from crewai.tools import BaseTool

from trading_crew.services.technical_analyzer import TechnicalAnalyzer


class AnalyzeMarketTool(BaseTool):
    """Compute technical indicators from OHLCV data."""

    name: str = "analyze_market"
    description: str = (
        "Compute technical indicators (EMA, RSI, Bollinger Bands, MACD, ATR) from "
        "OHLCV candle data. Input: JSON with 'symbol', 'exchange', and "
        "'candles' (list of {open, high, low, close, volume} objects)."
    )

    def _run(self, input_str: str) -> str:
        params = json.loads(input_str)
        symbol = params["symbol"]
        exchange = params.get("exchange", "unknown")
        candles = params.get("candles", [])

        try:
            analysis = TechnicalAnalyzer().analyze_from_candles(symbol, exchange, candles)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps(
            {
                "symbol": analysis.symbol,
                "current_price": analysis.current_price,
                "indicators": {k: round(v, 4) for k, v in analysis.indicators.items()},
                "metadata": analysis.metadata.model_dump(exclude_none=True),
                "timestamp": analysis.timestamp.isoformat(),
            },
            indent=2,
        )
