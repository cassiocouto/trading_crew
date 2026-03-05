"""Deterministic market intelligence pipeline for Phase 2.

Runs a concrete fetch -> analyze -> store cycle without relying on LLM text
handoff. This provides predictable behavior and lower token consumption.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from trading_crew.services.technical_analyzer import TechnicalAnalyzer

if TYPE_CHECKING:
    from trading_crew.models.market import OHLCV, MarketAnalysis
    from trading_crew.services.database_service import DatabaseService
    from trading_crew.services.exchange_service import ExchangeService
    from trading_crew.services.sentiment_service import SentimentSnapshot


class SentimentProvider(Protocol):
    """Protocol for sentiment enrichment providers."""

    def get_snapshot(self, symbol: str | None = None) -> SentimentSnapshot:
        """Return weighted sentiment snapshot."""


logger = logging.getLogger(__name__)


class MarketIntelligenceService:
    """Deterministic market intelligence workflow.

    For each symbol:
      1. Fetch ticker and candles from exchange
      2. Persist ticker and OHLCV to DB
      3. Compute technical indicators and regime metadata
      4. Return typed MarketAnalysis
    """

    def __init__(
        self,
        exchange_service: ExchangeService,
        db_service: DatabaseService,
        sentiment_service: SentimentProvider | None = None,
        regime_volatility_threshold: float = 0.03,
        regime_trend_threshold: float = 0.01,
    ) -> None:
        self._exchange = exchange_service
        self._db = db_service
        self._analyzer = TechnicalAnalyzer(
            volatility_threshold=regime_volatility_threshold,
            trend_threshold=regime_trend_threshold,
        )
        self._sentiment = sentiment_service

    async def run_cycle(
        self,
        symbols: list[str],
        timeframe: str,
        candle_limit: int = 120,
    ) -> dict[str, MarketAnalysis]:
        """Execute one full deterministic market-intelligence cycle."""
        analyses: dict[str, MarketAnalysis] = {}
        for symbol in symbols:
            analysis = await self._run_symbol(symbol, timeframe=timeframe, candle_limit=candle_limit)
            if analysis is not None:
                analyses[symbol] = analysis
        return analyses

    async def _run_symbol(self, symbol: str, timeframe: str, candle_limit: int) -> MarketAnalysis | None:
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            self._db.save_ticker(ticker)

            candles = await self._exchange.fetch_ohlcv(
                symbol=symbol, timeframe=timeframe, limit=candle_limit
            )
            self._db.save_ohlcv_batch(candles)

            analysis = self._analyze(symbol, candles)
            return analysis
        except Exception:
            logger.exception("Market pipeline failed for %s", symbol)
            return None

    def _analyze(self, symbol: str, candles: list[OHLCV]) -> MarketAnalysis:
        analysis = self._analyzer.analyze_from_candles(
            symbol=symbol,
            exchange=self._exchange.exchange_id,
            candles=candles,
        )
        metadata = analysis.metadata
        if self._sentiment is not None:
            snapshot = self._sentiment.get_snapshot(symbol=symbol)
            metadata.sentiment_score = float(snapshot.score)
            metadata.sentiment_confidence = float(snapshot.confidence)
            metadata.sentiment_sources = [s.name for s in snapshot.sources]
        return analysis.model_copy(update={"ohlcv_data": candles, "metadata": metadata})
