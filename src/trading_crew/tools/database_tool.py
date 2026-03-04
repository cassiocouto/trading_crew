"""CrewAI Tool for database operations.

Allows agents to store and retrieve trading data from the database.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from crewai.tools import BaseTool
from pydantic import Field

from trading_crew.services.database_service import DatabaseService
from trading_crew.utils.datetime import parse_iso_utc


class SaveTickerTool(BaseTool):
    """Save a ticker snapshot to the database for historical tracking."""

    name: str = "save_ticker"
    description: str = (
        "Save a ticker price snapshot to the database. Input: JSON with "
        "'symbol', 'exchange', 'bid', 'ask', 'last', 'volume_24h'."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        from trading_crew.models.market import Ticker

        params = json.loads(input_str)
        ticker = Ticker(
            symbol=params["symbol"],
            exchange=params["exchange"],
            bid=float(params["bid"]),
            ask=float(params["ask"]),
            last=float(params["last"]),
            volume_24h=float(params.get("volume_24h", 0)),
            timestamp=datetime.now(UTC),
        )
        self.db_service.save_ticker(ticker)
        return f"Saved ticker: {ticker.symbol} @ {ticker.last}"


class GetRecentCandlesTool(BaseTool):
    """Retrieve recent OHLCV candles from the database."""

    name: str = "get_recent_candles"
    description: str = (
        "Retrieve recent OHLCV candles from the database. Input: JSON with "
        "'symbol', 'exchange', 'timeframe' (e.g. '1h'), and optional 'limit'."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        params = json.loads(input_str)
        candles = self.db_service.get_recent_ohlcv(
            symbol=params["symbol"],
            exchange=params["exchange"],
            timeframe=params.get("timeframe", "1h"),
            limit=int(params.get("limit", 100)),
        )
        return json.dumps(
            [
                {
                    "timestamp": c.timestamp.isoformat(),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ],
            indent=2,
        )


class SaveOHLCVBatchTool(BaseTool):
    """Save OHLCV candles to the database."""

    name: str = "save_ohlcv_batch"
    description: str = (
        "Save a batch of OHLCV candles to the database. Input: JSON with "
        "'symbol', 'exchange', optional 'timeframe' (default '1h'), and "
        "'candles' list containing {timestamp, open, high, low, close, volume}."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        from trading_crew.models.market import OHLCV

        params = json.loads(input_str)
        symbol = params["symbol"]
        exchange = params["exchange"]
        timeframe = params.get("timeframe", "1h")
        raw_candles: list[dict[str, Any]] = params.get("candles", [])

        candles: list[OHLCV] = []
        for c in raw_candles:
            candles.append(
                OHLCV(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    timestamp=self._parse_timestamp(c.get("timestamp")),
                    open=float(c["open"]),
                    high=float(c["high"]),
                    low=float(c["low"]),
                    close=float(c["close"]),
                    volume=float(c.get("volume", 0)),
                )
            )

        count = self.db_service.save_ohlcv_batch(candles)
        return (
            f"Saved {count} OHLCV candles for {exchange} {symbol} "
            f"({timeframe})"
        )

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        return parse_iso_utc(value)
