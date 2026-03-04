"""Unit tests for deterministic sentiment service."""

from __future__ import annotations

import pytest

from trading_crew.services.sentiment_service import SentimentService


class _ResponseStub:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return

    def json(self) -> dict[str, object]:
        return self._payload


def _http_get_stub(url: str, timeout: float) -> _ResponseStub:
    del url, timeout
    return _ResponseStub({"data": [{"value": "70"}]})


@pytest.mark.unit
def test_sentiment_service_maps_fear_greed_and_weights_confidence() -> None:
    service = SentimentService(http_get=_http_get_stub)
    snapshot = service.get_snapshot(symbol="BTC/USDT")

    assert snapshot.score > 0
    assert 0 <= snapshot.confidence <= 1
    assert len(snapshot.sources) == 1
    assert snapshot.sources[0].name == "fear_greed_index"
    assert snapshot.sources[0].payload["value"] == 70


@pytest.mark.unit
def test_sentiment_service_returns_neutral_when_disabled() -> None:
    service = SentimentService(fear_greed_enabled=False, http_get=_http_get_stub)
    snapshot = service.get_snapshot(symbol="BTC/USDT")

    assert snapshot.score == 0.0
    assert snapshot.confidence == 0.0
    assert snapshot.sources == []
