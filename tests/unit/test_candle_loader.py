"""Tests for candle_loader module."""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from trading_crew.services.candle_loader import load_candles_csv

pytestmark = pytest.mark.unit


@pytest.fixture
def binance_csv_with_header(tmp_path: Path) -> Path:
    """CSV with a header row (Binance kline format, 12 columns)."""
    content = textwrap.dedent("""\
        open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_vol,taker_buy_quote_vol,ignore
        1704067200000,42000.0,42500.0,41800.0,42200.0,150.5,1704070799999,6340000,1200,80.0,3360000,0
        1704070800000,42200.0,42800.0,42100.0,42600.0,200.0,1704074399999,8520000,1500,100.0,4260000,0
        1704074400000,42600.0,43000.0,42400.0,42900.0,180.3,1704077999999,7700000,1300,90.0,3870000,0
        1704078000000,42900.0,43200.0,42700.0,43100.0,160.0,1704081599999,6890000,1100,85.0,3660000,0
    """)
    p = tmp_path / "with_header.csv"
    p.write_text(content)
    return p


@pytest.fixture
def binance_csv_headerless(tmp_path: Path) -> Path:
    """CSV without a header row (pure numeric, 12 columns)."""
    content = textwrap.dedent("""\
        1704067200000,42000.0,42500.0,41800.0,42200.0,150.5,1704070799999,6340000,1200,80.0,3360000,0
        1704070800000,42200.0,42800.0,42100.0,42600.0,200.0,1704074399999,8520000,1500,100.0,4260000,0
        1704074400000,42600.0,43000.0,42400.0,42900.0,180.3,1704077999999,7700000,1300,90.0,3870000,0
        1704078000000,42900.0,43200.0,42700.0,43100.0,160.0,1704081599999,6890000,1100,85.0,3660000,0
    """)
    p = tmp_path / "headerless.csv"
    p.write_text(content)
    return p


class TestHeaderedCSV:
    def test_loads_all_rows(self, binance_csv_with_header: Path) -> None:
        candles = load_candles_csv(binance_csv_with_header)
        assert len(candles) == 4

    def test_symbol_and_exchange_stamped(self, binance_csv_with_header: Path) -> None:
        candles = load_candles_csv(binance_csv_with_header, symbol="ETH/USDT", exchange="kraken")
        assert all(c.symbol == "ETH/USDT" for c in candles)
        assert all(c.exchange == "kraken" for c in candles)

    def test_timestamps_are_utc(self, binance_csv_with_header: Path) -> None:
        candles = load_candles_csv(binance_csv_with_header)
        assert candles[0].timestamp == datetime(2024, 1, 1, 0, 0, tzinfo=UTC)


class TestHeaderlessCSV:
    def test_loads_all_rows(self, binance_csv_headerless: Path) -> None:
        candles = load_candles_csv(binance_csv_headerless)
        assert len(candles) == 4

    def test_ohlcv_values(self, binance_csv_headerless: Path) -> None:
        candles = load_candles_csv(binance_csv_headerless)
        first = candles[0]
        assert first.open == 42000.0
        assert first.high == 42500.0
        assert first.low == 41800.0
        assert first.close == 42200.0
        assert first.volume == 150.5


class TestDateFiltering:
    def test_start_filter(self, binance_csv_with_header: Path) -> None:
        candles = load_candles_csv(
            binance_csv_with_header,
            start=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        )
        assert len(candles) == 3
        assert candles[0].timestamp >= datetime(2024, 1, 1, 1, 0, tzinfo=UTC)

    def test_end_filter(self, binance_csv_with_header: Path) -> None:
        candles = load_candles_csv(
            binance_csv_with_header,
            end=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        )
        assert len(candles) == 2
        assert candles[-1].timestamp <= datetime(2024, 1, 1, 1, 0, tzinfo=UTC)

    def test_start_and_end(self, binance_csv_with_header: Path) -> None:
        candles = load_candles_csv(
            binance_csv_with_header,
            start=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
            end=datetime(2024, 1, 1, 2, 0, tzinfo=UTC),
        )
        assert len(candles) == 2


class TestMaxBars:
    def test_truncation(self, binance_csv_with_header: Path) -> None:
        candles = load_candles_csv(binance_csv_with_header, max_bars=2)
        assert len(candles) == 2

    def test_no_truncation_when_under_limit(self, binance_csv_with_header: Path) -> None:
        candles = load_candles_csv(binance_csv_with_header, max_bars=100)
        assert len(candles) == 4


class TestResample:
    def test_1h_resample(self, tmp_path: Path) -> None:
        """Four 15m candles should collapse into one 1h candle."""
        rows: list[str] = []
        base_ts = 1704067200000  # 2024-01-01 00:00 UTC
        for i in range(4):
            ts = base_ts + i * 900_000  # 15 min intervals
            rows.append(f"{ts},100.0,110.0,90.0,105.0,50.0,0,0,0,0,0,0")
        p = tmp_path / "resample.csv"
        p.write_text("\n".join(rows) + "\n")

        candles = load_candles_csv(p, timeframe="15m", resample="1h")
        assert len(candles) == 1
        c = candles[0]
        assert c.timeframe == "1h"
        assert c.open == 100.0
        assert c.high == 110.0
        assert c.low == 90.0
        assert c.close == 105.0
        assert c.volume == 200.0  # 50 * 4

    def test_invalid_timeframe_raises(self, binance_csv_with_header: Path) -> None:
        with pytest.raises(ValueError, match="Unknown timeframe"):
            load_candles_csv(binance_csv_with_header, resample="2w")


class TestEdgeCases:
    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_candles_csv("/nonexistent/file.csv")

    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.csv"
        p.write_text("")
        candles = load_candles_csv(p)
        assert candles == []

    def test_malformed_rows_skipped(self, tmp_path: Path) -> None:
        content = "not,a,valid\n1704067200000,42000.0,42500.0,41800.0,42200.0,150.5\n"
        p = tmp_path / "malformed.csv"
        p.write_text(content)
        candles = load_candles_csv(p)
        assert len(candles) == 1
