"""Deterministic sentiment service (Phase 2b, optional).

Fetches external sentiment signals and returns a weighted aggregate score:
- score range: [-1.0, +1.0]
- confidence range: [0.0, 1.0]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

logger = logging.getLogger(__name__)

FNG_URL = "https://api.alternative.me/fng/?limit=1&format=json"

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class SentimentSource:
    """One sentiment source normalized to score/confidence."""

    name: str
    score: float
    confidence: float
    weight: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class SentimentSnapshot:
    """Aggregated sentiment snapshot."""

    score: float
    confidence: float
    sources: list[SentimentSource]


class SentimentService:
    """Optional sentiment enrichment service with confidence weighting."""

    def __init__(
        self,
        fear_greed_enabled: bool = True,
        fear_greed_weight: float = 1.0,
        timeout_seconds: float = 5.0,
        http_get: Callable[..., httpx.Response] | None = None,
    ) -> None:
        self._fear_greed_enabled = fear_greed_enabled
        self._fear_greed_weight = fear_greed_weight
        self._timeout_seconds = timeout_seconds
        self._http_get = http_get or httpx.get

    def get_snapshot(self, symbol: str | None = None) -> SentimentSnapshot:
        """Return weighted sentiment snapshot for current market context."""
        _ = symbol  # reserved for symbol-specific sources in future phases
        sources: list[SentimentSource] = []

        if self._fear_greed_enabled:
            source = self._fetch_fear_greed()
            if source is not None:
                sources.append(source)

        return self._aggregate_sources(sources)

    def _fetch_fear_greed(self) -> SentimentSource | None:
        """Fetch Fear & Greed Index and normalize to [-1, 1]."""
        try:
            response = self._http_get(FNG_URL, timeout=self._timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            value = int(payload["data"][0]["value"])
            score = max(-1.0, min(1.0, (value - 50) / 50))
            # We assume strong sentiment extremes are more informative than
            # neutral readings, so confidence scales with |score|.
            confidence = 0.55 + (abs(score) * 0.45)
            return SentimentSource(
                name="fear_greed_index",
                score=score,
                confidence=min(1.0, confidence),
                weight=max(0.0, self._fear_greed_weight),
                payload={"value": value},
            )
        except Exception:
            logger.exception("Failed to fetch Fear & Greed Index")
            return None

    @staticmethod
    def _aggregate_sources(sources: list[SentimentSource]) -> SentimentSnapshot:
        """Aggregate source scores using confidence-weighted mean."""
        if not sources:
            return SentimentSnapshot(score=0.0, confidence=0.0, sources=[])

        weighted_numerator = 0.0
        weighted_denominator = 0.0
        weight_sum = 0.0
        for source in sources:
            eff_weight = max(0.0, source.weight) * max(0.0, source.confidence)
            weighted_numerator += source.score * eff_weight
            weighted_denominator += eff_weight
            weight_sum += max(0.0, source.weight)

        if weighted_denominator == 0 or weight_sum == 0:
            return SentimentSnapshot(score=0.0, confidence=0.0, sources=sources)

        score = weighted_numerator / weighted_denominator
        confidence = min(1.0, weighted_denominator / weight_sum)
        return SentimentSnapshot(score=score, confidence=confidence, sources=sources)
