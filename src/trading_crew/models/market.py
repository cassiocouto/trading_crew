"""Market data models.

These models represent raw and processed market data flowing through the
Market Intelligence Crew. They are the primary input to all trading strategies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Ticker(BaseModel, frozen=True):
    """Real-time price snapshot from an exchange.

    Attributes:
        symbol: Trading pair (e.g. "BTC/USDT", "ETH/BRL").
        exchange: CCXT exchange identifier (e.g. "binance", "novadax").
        bid: Highest current buy order price.
        ask: Lowest current sell order price.
        last: Last traded price.
        volume_24h: 24-hour trading volume in base currency.
        timestamp: Exchange-reported timestamp.
    """

    symbol: str
    exchange: str
    bid: float
    ask: float
    last: float
    volume_24h: float = Field(ge=0)
    timestamp: datetime

    @property
    def spread(self) -> float:
        """Bid-ask spread as an absolute value."""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        """Bid-ask spread as a percentage of the mid price."""
        mid = (self.bid + self.ask) / 2
        if mid == 0:
            return 0.0
        return (self.spread / mid) * 100


class OHLCV(BaseModel, frozen=True):
    """Single candlestick (Open-High-Low-Close-Volume).

    Attributes:
        symbol: Trading pair.
        exchange: CCXT exchange identifier.
        timeframe: Candle period (e.g. "1m", "5m", "1h", "1d").
        timestamp: Candle open time.
        open: Opening price.
        high: Highest price during the period.
        low: Lowest price during the period.
        close: Closing price.
        volume: Trading volume in base currency.
    """

    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = Field(ge=0)


class OrderBookEntry(BaseModel, frozen=True):
    """Single level in an order book.

    Attributes:
        price: Price level.
        amount: Quantity available at this price.
    """

    price: float = Field(gt=0)
    amount: float = Field(gt=0)


class MarketAnalysis(BaseModel, frozen=True):
    """Processed market data with technical indicators.

    Produced by the Analyst Agent after processing raw market data.
    This is the primary input to trading strategies.

    Attributes:
        symbol: Trading pair.
        exchange: CCXT exchange identifier.
        timestamp: When this analysis was generated.
        current_price: Most recent price.
        indicators: Dictionary of computed indicator values. Keys are
            indicator names (e.g. "ema_12", "rsi_14", "bb_upper"),
            values are their numeric results.
        ohlcv_data: Recent OHLCV candles used for the analysis.
        metadata: Additional context (e.g. sentiment scores, volume profile).
    """

    symbol: str
    exchange: str
    timestamp: datetime
    current_price: float = Field(gt=0)
    indicators: dict[str, float] = Field(default_factory=dict)
    ohlcv_data: list[OHLCV] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_indicator(self, name: str) -> float | None:
        """Safely retrieve an indicator value by name."""
        return self.indicators.get(name)
