"""Unit tests for deterministic market intelligence service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from trading_crew.models.market import OHLCV, Ticker
from trading_crew.services.market_intelligence_service import MarketIntelligenceService
from trading_crew.services.sentiment_service import SentimentSnapshot, SentimentSource


class _ExchangeStub:
    exchange_id = "binance"

    def fetch_ticker(self, symbol: str) -> Ticker:
        return Ticker(
            symbol=symbol,
            exchange=self.exchange_id,
            bid=100.0,
            ask=101.0,
            last=100.5,
            volume_24h=1234.0,
            timestamp=datetime.now(UTC),
        )

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list[OHLCV]:
        start = datetime.now(UTC) - timedelta(minutes=limit)
        candles: list[OHLCV] = []
        for i in range(limit):
            close = 100.0 + i * 0.4
            candles.append(
                OHLCV(
                    symbol=symbol,
                    exchange=self.exchange_id,
                    timeframe=timeframe,
                    timestamp=start + timedelta(minutes=i),
                    open=close - 0.2,
                    high=close + 0.8,
                    low=close - 0.8,
                    close=close,
                    volume=1000 + i,
                )
            )
        return candles


class _DbStub:
    def __init__(self) -> None:
        self.ticker_count = 0
        self.candle_batch_sizes: list[int] = []

    def save_ticker(self, ticker: Ticker) -> None:
        self.ticker_count += 1

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> int:
        self.candle_batch_sizes.append(len(candles))
        return len(candles)


class _SentimentStub:
    def get_snapshot(self, symbol: str | None = None) -> SentimentSnapshot:
        _ = symbol
        return SentimentSnapshot(
            score=0.25,
            confidence=0.8,
            sources=[
                SentimentSource(
                    name="stub",
                    score=0.25,
                    confidence=0.8,
                    weight=1.0,
                    payload={},
                )
            ],
        )


@pytest.mark.unit
def test_run_cycle_fetches_analyzes_and_stores() -> None:
    exchange = _ExchangeStub()
    db = _DbStub()
    sentiment = _SentimentStub()
    service = MarketIntelligenceService(  # type: ignore[arg-type]
        exchange, db, sentiment_service=sentiment
    )

    analyses = service.run_cycle(
        symbols=["BTC/USDT", "ETH/USDT"],
        timeframe="1h",
        candle_limit=60,
    )

    assert set(analyses.keys()) == {"BTC/USDT", "ETH/USDT"}
    assert db.ticker_count == 2
    assert db.candle_batch_sizes == [60, 60]
    for analysis in analyses.values():
        assert "ema_fast" in analysis.indicators
        assert "macd_line" in analysis.indicators
        assert analysis.metadata["market_regime"] in {"trending", "ranging", "volatile"}
        assert analysis.metadata["sentiment_score"] == 0.25
        assert analysis.metadata["sentiment_confidence"] == 0.8
        assert analysis.metadata["sentiment_sources"] == ["stub"]
